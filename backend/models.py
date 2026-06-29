from __future__ import annotations
import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


def new_uuid() -> str:  # Genera un UUID único en formato string
    return str(uuid.uuid4())


class EstadoEnum(str, Enum):  # Enumeración de estados posibles para procedimientos, tareas y pasos
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADO = "COMPLETADO"
    ERROR = "ERROR"


class InfoBase(BaseModel):  # Modelo base con id, nombre e información común a varias entidades
    id: str = Field(default_factory=new_uuid)
    nombre: str
    informacion: Optional[str] = None


class CatalogItem(InfoBase):  # Item respaldado por el catálogo externo (Neo4j)
    stale: bool = False  # True si no se pudo refrescar en vivo y se muestra el último snapshot cacheado


class Action(CatalogItem):  # Acciones asociadas a pasos con tipo y parámetros
    tipo: Optional[str] = None
    parametros: Optional[dict] = Field(default_factory=dict)


class ObjectEntry(CatalogItem):  # Objeto que aparece en los pasos (hereda de CatalogItem)
    pass


class Condition(CatalogItem):  # Condición o requisito para ejecutar un paso
    pass


class Location(CatalogItem):  # Ubicación o localización relevante en un paso
    pass


class State(CatalogItem):  # Estado o situación dentro de un paso
    pass


class Step(InfoBase):  # Paso dentro de una tarea con orden y entidades asociadas (acciones, objetos, condiciones, etc.)
    orden: int
    estado: EstadoEnum = EstadoEnum.PENDIENTE
    completado_en: Optional[str] = None
    acciones: List[Action] = Field(default_factory=list)
    objetos: List[ObjectEntry] = Field(default_factory=list)
    condiciones: List[Condition] = Field(default_factory=list)
    locations: List[Location] = Field(default_factory=list)
    estados: List[State] = Field(default_factory=list)


class Task(InfoBase):  # Tarea dentro de un procedimiento con orden y lista de pasos
    orden: int
    estado: EstadoEnum = EstadoEnum.PENDIENTE
    completado_en: Optional[str] = None
    pasos: List[Step] = Field(default_factory=list)


class Procedure(InfoBase):  # Procedimiento principal que contiene una lista de tareas
    estado: EstadoEnum = EstadoEnum.PENDIENTE
    completado_en: Optional[str] = None
    tareas: List[Task] = Field(default_factory=list)


class CreateProcedure(BaseModel):  # Modelo para crear un nuevo procedimiento
    nombre: str
    informacion: Optional[str] = None


class CreateTask(BaseModel):  # Modelo para crear una nueva tarea dentro de un procedimiento
    nombre: str
    informacion: Optional[str] = None
    orden: int


class EditTask(BaseModel):  # Modelo para editar los datos de una tarea existente
    nombre: str
    informacion: Optional[str] = None


class CreateStep(BaseModel):  # Modelo para crear un nuevo paso dentro de una tarea
    nombre: str
    informacion: Optional[str] = None
    orden: int


class EditStep(BaseModel):  # Modelo para editar los datos de un paso existente
    nombre: str
    informacion: Optional[str] = None


class ReorderBody(BaseModel):  # Modelo para cambiar el orden de tareas o pasos
    orden: int


class ChangeEstadoBody(BaseModel):  # Modelo para cambiar el estado de un paso, tarea o procedimiento
    estado: EstadoEnum
