from pydantic import BaseModel


class FilamentBaseModel(BaseModel):
    def __hash__(self):
        return hash(self.model_dump_json())
