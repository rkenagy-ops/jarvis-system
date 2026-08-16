"""
orchestrator.py - core Jarvis multi-agent loop.

This wires together a small crew of CrewAI agents that share one LLM
(reached through the local litellm gateway) and call out to tools that are
exposed as MCP servers (see mcp_config.json). It is a starting scaffold,
not a finished product: review and extend each agent before relying on it.
"""

import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process, LLM

load_dotenv()

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "")
TRADING_REQUIRE_CONFIRMATION = os.getenv("TRADING_REQUIRE_CONFIRMATION", "true").lower() == "true"

brain = LLM(
    model="openai/kimi-k3",
    base_url=LITELLM_BASE_URL,
    api_key=LITELLM_MASTER_KEY,
)

jarvis_core = Agent(
    role="Jarvis Core",
    goal="Understand the user's request, break it into sub-tasks, and route each sub-task to the right specialist agent.",
    backstory="You are the central coordinator of a personal assistant system. You never guess when a specialist should be involved; you delegate.",
    llm=brain,
    allow_delegation=True,
    verbose=True,
)

researcher = Agent(
    role="Research Agent",
    goal="Answer questions and gather information using web browsing and crawling tools.",
    backstory="You are skilled at using browser-use and crawl4ai style tools to find accurate, current information.",
    llm=brain,
    verbose=True,
)

automation_agent = Agent(
    role="Automation Agent",
    goal="Carry out multi-step actions such as scheduling, document handling, and workflow triggers via n8n.",
    backstory="You turn instructions into concrete automations, and you always summarize what you changed.",
    llm=brain,
    verbose=True,
)

trading_agent = Agent(
    role="Trading Skill Agent",
    goal="Analyze market data and prepare trade recommendations, but never place a live order without explicit human confirmation.",
    backstory=(
        "You are a cautious trading analyst. You can use ccxt, freqtrade, nautilus_trader, "
        "vectorbt, backtrader, FinRL, lumibot, and TradingAgents for analysis and backtesting. "
        "You always stop and ask for confirmation before any real-money action."
    ),
    llm=brain,
    verbose=True,
)


def confirm_action(description: str) -> bool:
    """Blocking human confirmation gate. Required before any live trade or
    other irreversible action taken by a skill agent."""
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
    print("jarvis-system orchestrator. Type a request, or 'quit' to exit.")
    while True:
        user_request = input("you> ")
        if user_request.strip().lower() in {"quit", "exit"}:
            break
        crew = build_crew(user_request)
        result = crew.kickoff()
        print(result)
