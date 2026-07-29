"""
NEXUS Tool Base

Every tool in NEXUS must follow this structure.
"""


from abc import ABC, abstractmethod



class BaseTool(ABC):

    """
    Base class for all NEXUS tools.
    """


    name = "base"



    description = "Generic NEXUS tool"



    @abstractmethod
    def can_handle(
        self,
        query: str
    ) -> bool:

        """
        Determines if this tool can handle a request.
        """

        pass



    @abstractmethod
    def execute(
        self,
        query: str
    ):

        """
        Executes the tool action.
        """

        pass



    def info(self):

        return {

            "name": self.name,

            "description": self.description

        }
