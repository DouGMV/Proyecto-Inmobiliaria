"""Interfaz que todo proveedor de IA implementa (docs/arquitectura.md §7).

El resto del sistema solo conoce estas clases. Ningún servicio importa el SDK
de un proveedor: si mañana se cambia Gemini por otro, se escribe otra
implementación y se cambia IA_PROVEEDOR, sin tocar servicios ni vistas.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class RolMensaje(StrEnum):
    SISTEMA = "sistema"  # instrucciones para el modelo, no las ve el usuario
    USUARIO = "usuario"
    MODELO = "modelo"


class TareaEmbedding(StrEnum):
    """Para qué es el vector. Gemini da mejores resultados si lo sabe.

    DOCUMENTO al indexar fragmentos y CONSULTA al vectorizar la pregunta del
    usuario (spec 005, §6).
    """

    DOCUMENTO = "documento"
    CONSULTA = "consulta"


@dataclass(frozen=True)
class Mensaje:
    rol: RolMensaje
    contenido: str


@dataclass(frozen=True)
class Herramienta:
    """Función del sistema que el modelo puede pedir que se ejecute.

    La declaración describe la función al proveedor. ejecutar es la función
    autorizada del servidor que obtiene el dato cuando el modelo lo solicita.
    """

    nombre: str
    descripcion: str
    parametros: dict = field(default_factory=dict)
    ejecutar: Callable[..., dict] | None = None


@dataclass(frozen=True)
class RespuestaIA:
    texto: str
    modelo: str
    # None cuando el proveedor no reporta el consumo: no es lo mismo que cero
    # (contrato con la bitácora del agente, spec 015).
    tokens_entrada: int | None
    tokens_salida: int | None


class ProveedorIANoDisponible(Exception):
    """El proveedor no respondió o rechazó la petición.

    El servicio la traduce a AgenteNoDisponible (503), nunca a un 500.
    """


class ProveedorIA(ABC):
    @abstractmethod
    def generar_respuesta(
        self,
        *,
        mensajes: list[Mensaje],
        herramientas: list[Herramienta] | None = None,
    ) -> RespuestaIA:
        """Envía la conversación al modelo y devuelve su respuesta."""

    @abstractmethod
    def generar_embedding(self, *, texto: str, tarea: TareaEmbedding) -> list[float]:
        """Devuelve el vector de un texto."""

    @abstractmethod
    def generar_embeddings_lote(
        self, *, textos: list[str], tarea: TareaEmbedding
    ) -> list[list[float]]:
        """Devuelve un vector por texto, en el mismo orden."""
