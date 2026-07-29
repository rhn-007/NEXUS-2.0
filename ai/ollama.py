import requests
from utils.logger import setup_logger


logger = setup_logger(__name__)


class OllamaClient:


    def __init__(self):

        self.url = "http://localhost:11434/api/chat"

        self.model = "llama3"

        logger.info(
            "Ollama client ready"
        )



    def generate_response(
        self,
        message,
        context=None
    ):


        try:


            messages = []


            if context:

                messages.append(
                    {
                        "role": "system",
                        "content": str(context)
                    }
                )


            messages.append(
                {
                    "role": "user",
                    "content": message
                }
            )



            payload = {

                "model": self.model,

                "messages": messages,

                "stream": False

            }



            logger.info(
                "Sending request to Ollama..."
            )


            response = requests.post(

                self.url,

                json=payload,

                timeout=120

            )


            response.raise_for_status()



            data = response.json()



            return data["message"]["content"]



        except Exception as e:


            logger.error(

                f"Ollama error: {e}"

            )


            return (
                f"Ollama error: {e}"
            )
