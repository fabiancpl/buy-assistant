import logging
import requests
from typing import List

from pydantic import BaseModel, Field

from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import ChatPromptTemplate
from langchain.vectorstores import Chroma


logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)


class CategoryResponse(BaseModel):
    name: str = Field(description="Nombre de la categoría")
    questions: List[str] = Field(description="Preguntas asociadas a la categoría")

class BuyAssistantResponse(BaseModel):
    message: str = Field(description="Mensaje de bienvenida")
    categories: List[CategoryResponse] = Field(description="Categorías asociadas a los productos identificados")

class BuyAssistant():
    # ChatGPT parameters
    MODEL = "gpt-4"
    TEMPERATURE = 0.0
    
    # ChromaDB parameters
    COLLECTION_NAME = "MELI_CATEGORY_TREE"
    VECTOR_DIR = "data/chroma"
    
    # Buy assistant parameters
    CAROUSELS_TO_BUILD = 4
    QUESTIONS_BY_CATEGORY = 2
    ITEMS_BY_CAROUSEL = 5
    
    PROMPT_TEMPLATE_STR = """
    Eres un asistente de compra en un marketplace online. Tu tarea es ayudar a los usuarios a encontrar lo que necesitan comprar a partir de una intención, necesidad o deseo que manifiesten.

    Tu tarea es:
    - Generar un mensaje de bienvenida ofreciendo ayuda al usuario. Este mensaje de bienvenida también puede estar relacionado al input ingresado.
    - Identificar el top {carousels_to_build} de productos asociados con el input ingresado y que el usuario deberá comprar para cumplir su intención, necesidad o deseo.
    - Para cada producto identificado, determinar las categorías de productos a las que pertenecen. 
    - Para cada categoría, seleccionar las {questions_by_category} preguntas más comunes que podrían hacer los usuarios previo a la compra. 

    El input ingresado por el usuario se encuentra delimitado por triple backticks: ```{search_input}```.

    {format_instructions}
    """
    
    
    def __init__(self):
        # Creating the chat
        self.chat_openai = ChatOpenAI(
            model_name=self.MODEL,
            temperature=self.TEMPERATURE
        )
        
        # Creating the vector store
        self.vectorstore = Chroma(
            embedding_function=OpenAIEmbeddings(),
            collection_name=self.COLLECTION_NAME,
            persist_directory=self.VECTOR_DIR
        )
        
        # Creating the prompt template and output parser
        self.prompt_template = ChatPromptTemplate.from_template(self.PROMPT_TEMPLATE_STR)
        self.output_parser = PydanticOutputParser(pydantic_object=BuyAssistantResponse)
    
    
    def obj_to_dict(self, response_obj):
        response_dict = response_obj.__dict__

        categories_dict = []
        for category_obj in response_dict["categories"]:
            categories_dict.append(category_obj.__dict__)

        response_dict["categories"] = categories_dict
        
        return response_dict
    
    
    def chat(self, search_input):
        # Building the prompt
        logging.info("1. Building the prompt")
        prompt = self.prompt_template.format_messages(
            carousels_to_build=self.CAROUSELS_TO_BUILD,
            questions_by_category=self.QUESTIONS_BY_CATEGORY,
            search_input=search_input,
            format_instructions=self.output_parser.get_format_instructions()
        )
        
        # Calling the chat and parsing the response
        logging.info("2. Calling the chat and parsing the response")
        response = self.chat_openai(prompt)
        response_obj = self.output_parser.parse(response.content)
        response_dict = self.obj_to_dict(response_obj)
        
        # Matching with MeLi categories
        logging.info("3. Matching with MeLi categories")
        categories = []
        for category in list(map(lambda x: x["name"], response_dict["categories"])):
            try:
                result = self.vectorstore.similarity_search_with_score(query=category, k=1)[0]
                categories.append({
                    "category_raw": category,
                    "category_id": result[0].page_content.split("\n")[4].replace("CATEGORY_ID_L3: ", ""),
                    "category_name": result[0].page_content.split("\n")[5].replace("CATEGORY_NAME_L3: ", ""),
                    "domain_id": result[0].page_content.split("\n")[7].replace("DOMAIN_ID: ", ""),
                    "similarity_score": result[1]
                })
            except IndexError:
                logging.warning("Category not matched for:", category)
        
        # Calling Search API for each MeLi category
        logging.info("4. Calling Search API for each MeLi category")
        uq_category_ids = set(map(lambda x: x["category_id"], categories))
        search_results = []
        for category_id in uq_category_ids:
            r = requests.get(f"http://api.mercadolibre.com/sites/MLA/search?limit=50&sort=relevance&category={category_id}")
            results = r.json()["results"]

            results = [{
                "item_id": result["id"],
                "title": result["title"] if "title" in result else "",
                "permalink": result["permalink"] if "permalink" in result else "",
                "thumbnail": result["thumbnail"] if "thumbnail" in result else "",
                "category_id": result["category_id"] if "category_id" in result else "",
                "domain_id": result["domain_id"] if "domain_id" in result else ""
            } for result in results]

            search_results.append({
                "category_id": category_id,
                "results": results
            })
        
        # Building the carousels
        logging.info("5. Building the carousels")
        carousels = []
        for category in categories:
            carousel = {}
            items = list(filter(
                lambda x: x["domain_id"] == category["domain_id"],
                list(filter(lambda x: x["category_id"] == category["category_id"], search_results))[0]["results"]
            ))[:self.ITEMS_BY_CAROUSEL]

            carousel["items"] = items
            carousels.append({**carousel, **category})
        
        # Joining carousels with category questions
        logging.info("6. Joining carousels with category questions")
        for carousel in carousels:
            carousel["questions"] = list(filter(lambda x: x["name"] == carousel["category_raw"], response_dict["categories"]))[0]["questions"]
        
        return {
            "message": response_dict["message"],
            "carousels": carousels
        }
