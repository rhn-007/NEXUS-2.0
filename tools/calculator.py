"""
NEXUS Calculator Tool

Handles basic mathematical expressions.
"""

import re
import ast
import operator



class CalculatorTool:


    name = "calculator"



    def can_handle(
        self,
        text
    ):

        if not text:

            return False


        text = text.lower()


        keywords = [

            "calculate",

            "what is",

            "solve",

        ]


        math_symbols = [

            "+",

            "-",

            "*",

            "/",

            "%"

        ]


        return (

            any(
                word in text
                for word in keywords
            )

            and

            any(
                symbol in text
                for symbol in math_symbols
            )

        )



    def execute(
        self,
        text
    ):


        try:


            expression = self.extract_expression(
                text
            )


            if not expression:

                return None



            result = self.safe_eval(
                expression
            )


            return str(result)



        except Exception:


            return None




    def extract_expression(
        self,
        text
    ):


        text = text.lower()


        text = text.replace(

            "what is",

            ""

        )


        text = text.replace(

            "calculate",

            ""

        )


        text = text.replace(

            "solve",

            ""

        )


        return text.strip()




    def safe_eval(
        self,
        expression
    ):


        allowed = {

            ast.Add: operator.add,

            ast.Sub: operator.sub,

            ast.Mult: operator.mul,

            ast.Div: operator.truediv,

            ast.Mod: operator.mod

        }



        def evaluate(node):


            if isinstance(
                node,
                ast.Constant
            ):

                return node.value



            if isinstance(
                node,
                ast.BinOp
            ):

                operation = allowed[
                    type(node.op)
                ]


                return operation(

                    evaluate(node.left),

                    evaluate(node.right)

                )


            raise ValueError(
                "Invalid expression"
            )



        tree = ast.parse(

            expression,

            mode="eval"

        )


        return evaluate(
            tree.body
        )
