"""
Parked CrewAI CLI loop. The live OS loop is `python -m app` (HUD + autonomy). GitHub docs: README.md / AGENTS.md (5.8.2).

The live system is Super Jarvis: `python -m app` / start.ps1
This file keeps the original crew for people who want a terminal crew.

Brain order:
1. SpaceXAI (XAI_API_KEY) via https://api.x.ai/v1
2. Local LiteLLM / Kimi gateway
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from crewai import Agent, Crew, LLM, Process, Task

load_dotenv()

TRADING_REQUIRE_CONFIRMATION = os.getenv("TRADING_REQUIRE_CONFIRMATION", "true").lower() == "true"
XAI_API_KEY = (os.getenv("XAI_API_KEY") or "").strip()
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")
MODEL = os.getenv("JARVIS_MODEL", "grok-4.6")


def build_llm() -> LLM:
    if XAI_API_KEY:
        return LLM(
            model=f"openai/{MODEL}",
            base_url="https://api.x.ai/v1",
            api_key=XAI_API_KEY,
        )
    return LLM(
        model="openai/kimi-k3",
        base_url=LITELLM_BASE_URL,
        api_key=LITELLM_MASTER_KEY,
    )


brain = build_llm()

jarvis_core = Agent(
    role="Jarvis Core",
    goal="Understand the request, break it into sub-tasks, and route each to the right specialist.",
    backstory="Central coordinator of rkenagy-ops jarvis-system. You delegate instead of guessing.",
    llm=brain,
    allow_delegation=True,
    verbose=True,
)

researcher = Agent(
    role="Research Agent",
    goal="Answer questions with current information.",
    backstory="You use live search and crawling tools. You cite sources.",
    llm=brain,
    verbose=True,
)

automation_agent = Agent(
    role="Automation Agent",
    goal="Turn instructions into concrete automations and summarize what changed.",
    backstory="You schedule, handle documents, and trigger n8n workflows.",
    llm=brain,
    verbose=True,
)

trading_agent = Agent(
    role="Trading Skill Agent",
    goal="Analyze markets and prepare recommendations. Never place a live order without explicit human confirmation.",
    backstory=(
        "Cautious trading analyst. Paper mode is the default. "
        "Any real-money path must call confirm_action first."
    ),
    llm=brain,
    verbose=True,
)


def confirm_action(description: str) -> bool:
    """Blocking human confirmation gate before any live trade or irreversible action."""
    if not TRADING_REQUIRE_CONFIRMATION:
        return True
    answer = input(f"CONFIRM REQUIRED: {description}\nType 'yes' to proceed: ")
    return answer.strip().lower() == "yes"


def build_crew(user_request: str) -> Crew:
    task = Task(
        description=f"Handle this request from the user: {user_request}",
        expected_output="A clear, direct answer or a summary of actions taken.",
        agent=jarvis_core,
    )
    return Crew(
        agents=[jarvis_core, researcher, automation_agent, trading_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )


if __name__ == "__main__":
    print("jarvis-system CrewAI loop. Prefer `python -m app` for the HUD.")
    print("Type a request, or 'quit' to exit.")
    while True:
        user_request = input("you> ")
        if user_request.strip().lower() in {"quit", "exit"}:
            break
        print(build_crew(user_request).kickoff())
