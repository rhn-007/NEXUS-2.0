"""Main controller for the NEXUS assistant."""

from dotenv import load_dotenv

from ai.ollama import OllamaClient
from memory.memory_manager import MemoryManager
from core.response_style import ResponseStyleController
from core.conversation import ConversationManager
from core.input_manager import InputManager
from core.action_planner import ActionPlanner
from voice.speaker import Speaker

from tools.registry import ToolRegistry
from tools.router import ToolRouter
from tools.browser import BrowserTool
from tools.application import ApplicationTool

from ui.status import set_status, clear_status
from utils.logger import setup_logger


load_dotenv()
logger = setup_logger(__name__)


class NexusAssistant:
    def __init__(self):
        logger.info("Initializing NEXUS...")

        self.memory = MemoryManager()

        self.conversation = ConversationManager()
        self.conversation.load_history(
            self.memory.get_recent_messages(limit=20)
        )

        self.response_style = ResponseStyleController()
        self.llm = OllamaClient()

        self.input_manager = InputManager()
        self.speaker = Speaker()

        self.tool_registry = ToolRegistry()
        self.register_tools()
        self.tool_router = ToolRouter(self.tool_registry)
        self.action_planner = ActionPlanner(
            self.llm,
            self.tool_router
        )

        self.status = "READY"
        logger.info("NEXUS initialized successfully.")

    def start(self):
        print("\n🤖 N.E.X.U.S 2.0 Online\n")

        while True:
            user_input = self.input_manager.get_input()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "shutdown"):
                self.speaker.speak("Goodbye.")
                print("Goodbye 👋")
                break

            response = self.process_input(user_input)
            print("\nNEXUS:", response, "\n")

    def register_tools(self):
        self.tool_registry.register(BrowserTool())
        self.tool_registry.register(ApplicationTool())

    def _complete_turn(self, user_input, response):
        self.conversation.add_assistant_message(response)
        self.memory.save_conversation(user_input, response)
        self.speaker.speak(response)
        return response

    def process_input(self, user_input):
        if not user_input or not user_input.strip():
            return ""

        self.status = "PROCESSING"
        set_status("Thinking")
        logger.info("User: %s", user_input)

        try:
            self.conversation.add_user_message(user_input)

            memory_response = self.check_memory(user_input)
            if memory_response:
                return self._complete_turn(user_input, memory_response)

            self.memory.process_memory(user_input)

            # Multi-step requests are planned and validated before execution.
            planned_result = self.action_planner.execute_if_needed(user_input)
            if planned_result is not None:
                return self._complete_turn(
                    user_input,
                    planned_result.message
                )

            tool_result = self.tool_router.execute(user_input)

            if tool_result.handled:
                return self._complete_turn(
                    user_input,
                    tool_result.message
                )

            context = self.conversation.get_context(
                self.memory.build_context()
            )

            response = self.llm.generate_response(
                user_input,
                context
            )
            response = self.response_style.refine(response)

            return self._complete_turn(user_input, response)

        except Exception as error:
            logger.exception("NEXUS error")
            return f"Error: {error}"

        finally:
            self.status = "READY"
            clear_status()

    def check_memory(self, user_input):
        return self.memory.handle_memory_query(user_input)
