class MemoryItem:


    def __init__(
        self,
        key,
        value,
        category="general"
    ):

        self.key = key

        self.value = value

        self.category = category



    def to_dict(self):

        return {

            "key": self.key,

            "value": self.value,

            "category": self.category

        }
