"""Branch Queue — gestor de colas por tipo de servicio para Banco Meridional.

Uso:
    python branch_queue.py

Las notas de diseño (eficiencia y concurrencia) están en DESIGN.md.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

SERVICE_TYPES = ("deposito", "retiro", "gestion_cuenta")

SERVICE_LABELS = {
    "deposito": "Depósitos",
    "retiro": "Retiros",
    "gestion_cuenta": "Gestión de cuenta",
}


class InvalidServiceTypeError(ValueError):
    """Se lanza cuando se usa un tipo de servicio no reconocido."""


class EmptyQueueError(LookupError):
    """Se lanza cuando se intenta llamar/consultar una cola sin clientes."""


@dataclass(frozen=True)
class Ticket:
    number: int
    client_name: str
    service_type: str
    issued_at: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        hora = self.issued_at.strftime("%H:%M:%S")
        return f"#{self.number:03d} {self.client_name} ({self.service_type}, {hora})"


class BranchQueue:
    """Mantiene una cola FIFO independiente por tipo de servicio.

    Cada cola es un `deque`, así que encolar (append) y desencolar (popleft)
    son O(1) sin importar cuántos clientes esperen en las demás colas.
    """

    def __init__(self, service_types=SERVICE_TYPES):
        self._queues = {service: deque() for service in service_types}
        self._next_number = 1

    @property
    def service_types(self):
        return tuple(self._queues)

    def _validate_service(self, service_type) -> str:
        normalized = str(service_type).strip().lower()
        if normalized not in self._queues:
            valid = ", ".join(self._queues)
            raise InvalidServiceTypeError(
                f"Tipo de servicio inválido: '{service_type}'. "
                f"Los válidos son: {valid}."
            )
        return normalized

    def issue_ticket(self, client_name, service_type) -> Ticket:
        service = self._validate_service(service_type)
        name = str(client_name).strip()
        if not name:
            raise ValueError("El nombre del cliente no puede estar vacío.")

        ticket = Ticket(number=self._next_number, client_name=name, service_type=service)
        self._next_number += 1
        self._queues[service].append(ticket)
        return ticket

    def call_next(self, service_type) -> Ticket:
        service = self._validate_service(service_type)
        queue = self._queues[service]
        if not queue:
            raise EmptyQueueError(f"No hay clientes esperando para '{service}'.")
        return queue.popleft()

    def peek_next(self, service_type) -> Ticket:
        service = self._validate_service(service_type)
        queue = self._queues[service]
        if not queue:
            raise EmptyQueueError(f"No hay clientes esperando para '{service}'.")
        return queue[0]

    def list_waiting(self) -> dict:
        # Copias en forma de lista para que el llamador no pueda mutar las colas internas.
        return {service: list(queue) for service, queue in self._queues.items()}

    def stats(self) -> dict:
        counts = {service: len(queue) for service, queue in self._queues.items()}
        counts["total"] = sum(counts.values())
        return counts


class BranchQueueCLI:
    """Menú de texto en bucle sobre una instancia de BranchQueue."""

    MENU = """
===== Banco Meridional — Gestor de colas =====
1. Emitir nuevo ticket
2. Llamar al siguiente cliente
3. Ver siguiente cliente (sin retirarlo)
4. Ver lista de espera
5. Ver estadísticas
6. Salir
"""

    def __init__(self, branch_queue: BranchQueue):
        self.queue = branch_queue
        self.actions = {
            "1": self.issue_ticket,
            "2": self.call_next,
            "3": self.peek_next,
            "4": self.show_waiting,
            "5": self.show_stats,
        }

    def run(self) -> None:
        while True:
            print(self.MENU)
            choice = self._input("Elige una opción: ")
            if choice is None or choice == "6":
                print("¡Hasta luego!")
                return
            action = self.actions.get(choice)
            if action is None:
                print("Opción no válida. Introduce un número del 1 al 6.")
                continue
            try:
                action()
            except (InvalidServiceTypeError, EmptyQueueError, ValueError) as error:
                print(f"Error: {error}")

    @staticmethod
    def _input(prompt):
        """Lee una línea; devuelve None si la entrada se cierra (Ctrl+D / Ctrl+C)."""
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

    def _ask_service(self) -> str:
        services = self.queue.service_types
        print("Tipos de servicio:")
        for index, service in enumerate(services, start=1):
            print(f"  {index}. {service} — {SERVICE_LABELS.get(service, service)}")
        answer = self._input("Servicio (número o nombre): ")
        if answer is None:
            raise ValueError("Operación cancelada.")
        if answer.isdigit() and 1 <= int(answer) <= len(services):
            return services[int(answer) - 1]
        return answer  # BranchQueue valida y rechaza los nombres inválidos

    def issue_ticket(self) -> None:
        name = self._input("Nombre del cliente: ")
        if name is None:
            raise ValueError("Operación cancelada.")
        service = self._ask_service()
        ticket = self.queue.issue_ticket(name, service)
        print(f"Ticket emitido: {ticket}")

    def call_next(self) -> None:
        ticket = self.queue.call_next(self._ask_service())
        print(f"Llamando a: {ticket}")

    def peek_next(self) -> None:
        ticket = self.queue.peek_next(self._ask_service())
        print(f"Siguiente en la cola: {ticket}")

    def show_waiting(self) -> None:
        for service, tickets in self.queue.list_waiting().items():
            print(f"\n[{SERVICE_LABELS.get(service, service)}]")
            if not tickets:
                print("  (sin clientes en espera)")
            for position, ticket in enumerate(tickets, start=1):
                print(f"  {position}. {ticket}")

    def show_stats(self) -> None:
        stats = self.queue.stats()
        print("\nClientes en espera:")
        for service in self.queue.service_types:
            print(f"  {SERVICE_LABELS.get(service, service):<20} {stats[service]}")
        print(f"  {'Total':<20} {stats['total']}")


def main() -> None:
    BranchQueueCLI(BranchQueue()).run()


if __name__ == "__main__":
    main()
