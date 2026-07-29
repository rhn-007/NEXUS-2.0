"""
NEXUS Tool Response

Standard response format for every tool.
"""



class ToolResponse:


    def __init__(
        self,
        success=True,
        message="",
        data=None
    ):

        self.success = success

        self.message = message

        self.data = data or {}



    def to_dict(self):

        return {

            "success": self.success,

            "message": self.message,

            "data": self.data

        }



    @staticmethod
    def success(
        message,
        data=None
    ):

        return ToolResponse(

            True,

            message,

            data

        )



    @staticmethod
    def failure(
        message,
        data=None
    ):

        return ToolResponse(

            False,

            message,

            data

        )



    def __str__(self):

        return self.message
