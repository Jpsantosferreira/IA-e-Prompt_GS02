# Chatbot Citizen Assist

import asyncio
import os
import json
from dotenv import load_dotenv

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    Runner,
    SQLiteSession,
    TResponseInputItem,
    function_tool,
    input_guardrail,
    output_guardrail,
)
from typing import Union

load_dotenv()

def carregar_fichas():
    fichas = {}
    fichas_dir = 'fichas'
    if os.path.exists(fichas_dir):
        for filename in os.listdir(fichas_dir):
            if filename.endswith('.md'):
                with open(os.path.join(fichas_dir, filename), 'r', encoding='utf-8') as f:
                    fichas[filename.replace('.md', '')] = f.read()
    return fichas

BASE_CONHECIMENTO = carregar_fichas()

@function_tool
def consultar_base_conhecimento(assunto: str) -> str:
    """Consulta a base de conhecimento (fichas) para encontrar informações sobre documentos.
    Assuntos válidos: FC-01_rg_segunda_via, FC-02_cpf, FC-03_titulo_de_eleitor, 
    FC-04_carteira_de_trabalho, FC-05_certidoes, FC-06_cnh_renovacao, FC-07_regras_gerais.
    """
    for key, conteudo in BASE_CONHECIMENTO.items():
        if assunto.lower() in key.lower():
            return conteudo
    return "Ficha não encontrada. Consulte as categorias disponíveis."

@function_tool
def listar_fichas_disponiveis() -> str:
    return "Fichas disponíveis: " + ", ".join(BASE_CONHECIMENTO.keys())

# Guardrails
TERMOS_INJECAO = ("ignore", "esqueça suas instruções", "prompt", "nova regra", "sistema:")
TERMOS_DADOS_SENSIVEIS = ("cpf:", "rg:", "telefone:", "celular:", "endereco", "endereço")
PADROES_CPF = ["123.456.789-09", "12345678909"] # Exemplos simplificados para o teste

@input_guardrail(run_in_parallel=False)
def bloquear_prompt_injection(ctx, agent, user_input: Union[str, list[TResponseInputItem]]) -> GuardrailFunctionOutput:
    texto = (user_input if isinstance(user_input, str) else str(user_input)).lower()
    encontrou = any(termo in texto for termo in TERMOS_INJECAO)
    return GuardrailFunctionOutput(
        output_info="Tentativa de prompt injection detectada" if encontrou else "Ok",
        tripwire_triggered=encontrou,
    )

@input_guardrail(run_in_parallel=False)
def bloquear_dados_sensiveis(ctx, agent, user_input: Union[str, list[TResponseInputItem]]) -> GuardrailFunctionOutput:
    texto = (user_input if isinstance(user_input, str) else str(user_input)).lower()
    encontrou = any(termo in texto for termo in TERMOS_DADOS_SENSIVEIS) or any(cpf in texto for cpf in PADROES_CPF)
    return GuardrailFunctionOutput(
        output_info="Dado sensível detectado" if encontrou else "Ok",
        tripwire_triggered=encontrou,
    )

INSTRUCOES = """Você é o Citizen Assist AI, assistente da Central do Cidadão de Aurora.
Regras:
1. Use APENAS as informações retornadas pela ferramenta `consultar_base_conhecimento`.
2. Se a informação não estiver nas fichas, diga que não encontrou e oriente a consultar o órgão competente. Nunca invente.
3. Cite sempre a ficha de origem (ex: FC-01) e a data de verificação nas suas respostas.
4. Inclua um aviso informando que você não é o canal oficial e as informações devem ser confirmadas no site do órgão.
5. Seja claro, objetivo e use linguagem acessível.
"""

agente_cidadao = Agent(
    name="Citizen Assist AI",
    instructions=INSTRUCOES,
    model="gpt-4o-mini",
    tools=[consultar_base_conhecimento, listar_fichas_disponiveis],
    input_guardrails=[bloquear_prompt_injection, bloquear_dados_sensiveis]
)

async def main():
    print("Bem-vindo ao Citizen Assist AI! Digite 'sair' para encerrar.")
    sessao = SQLiteSession("sessao_cidadao")
    while True:
        entrada = input("Você: ")
        if entrada.lower() == 'sair': break
        try:
            res = await Runner.run(agente_cidadao, entrada, session=sessao)
            print(f"Assistente: {res.final_output}\n")
        except InputGuardrailTripwireTriggered:
            print("Assistente: Detectei um padrão não permitido (possível dado pessoal ou instrução inválida). Por favor, reformule sua pergunta sem incluir dados sensíveis.\n")
        except Exception as e:
            print("Assistente: Desculpe, não entendi sua solicitação. Tente novamente.\n")

if __name__ == "__main__":
    asyncio.run(main())
