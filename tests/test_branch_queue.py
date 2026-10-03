"""Pruebas de BranchQueue y del menú CLI.

Ejecutar desde la raíz del proyecto:
    python -m unittest
"""

import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

from branch_queue import (
    BranchQueue,
    BranchQueueCLI,
    EmptyQueueError,
    InvalidServiceTypeError,
    Ticket,
)


class IssueTicketTests(unittest.TestCase):
    def setUp(self):
        self.queue = BranchQueue()

    def test_returns_ticket_with_all_fields(self):
        ticket = self.queue.issue_ticket("Ana", "deposito")

        self.assertIsInstance(ticket, Ticket)
        self.assertEqual(ticket.number, 1)
        self.assertEqual(ticket.client_name, "Ana")
        self.assertEqual(ticket.service_type, "deposito")
        self.assertIsInstance(ticket.issued_at, datetime)

    def test_numbers_are_global_across_services(self):
        numbers = [
            self.queue.issue_ticket("Ana", "deposito").number,
            self.queue.issue_ticket("Luis", "retiro").number,
            self.queue.issue_ticket("Eva", "gestion_cuenta").number,
            self.queue.issue_ticket("Juan", "deposito").number,
        ]
        self.assertEqual(numbers, [1, 2, 3, 4])

    def test_numbers_are_not_reused_after_calling(self):
        self.queue.issue_ticket("Ana", "deposito")
        self.queue.call_next("deposito")
        self.assertEqual(self.queue.issue_ticket("Luis", "deposito").number, 2)

    def test_invalid_service_is_rejected_with_message(self):
        with self.assertRaises(InvalidServiceTypeError) as context:
            self.queue.issue_ticket("Ana", "hipoteca")

        self.assertIn("hipoteca", str(context.exception))
        self.assertIn("deposito", str(context.exception))
        self.assertEqual(self.queue.stats()["total"], 0)

    def test_invalid_service_does_not_consume_a_number(self):
        with self.assertRaises(InvalidServiceTypeError):
            self.queue.issue_ticket("Ana", "hipoteca")
        self.assertEqual(self.queue.issue_ticket("Ana", "retiro").number, 1)

    def test_service_type_is_normalized(self):
        ticket = self.queue.issue_ticket("Ana", "  RETIRO ")
        self.assertEqual(ticket.service_type, "retiro")

    def test_empty_client_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.queue.issue_ticket("   ", "deposito")


class CallAndPeekTests(unittest.TestCase):
    def setUp(self):
        self.queue = BranchQueue()

    def test_call_next_is_fifo_within_a_service(self):
        self.queue.issue_ticket("Ana", "deposito")
        self.queue.issue_ticket("Luis", "retiro")
        self.queue.issue_ticket("Eva", "deposito")
        self.queue.issue_ticket("Juan", "deposito")

        called = [self.queue.call_next("deposito").client_name for _ in range(3)]
        self.assertEqual(called, ["Ana", "Eva", "Juan"])

    def test_call_next_only_touches_its_own_service(self):
        self.queue.issue_ticket("Ana", "retiro")
        self.queue.issue_ticket("Luis", "deposito")

        self.assertEqual(self.queue.call_next("deposito").client_name, "Luis")
        self.assertEqual(self.queue.stats()["retiro"], 1)

    def test_call_next_on_empty_queue_raises_descriptive_error(self):
        self.queue.issue_ticket("Ana", "retiro")

        with self.assertRaises(EmptyQueueError) as context:
            self.queue.call_next("deposito")
        self.assertIn("deposito", str(context.exception))

    def test_peek_next_does_not_remove(self):
        self.queue.issue_ticket("Ana", "gestion_cuenta")

        self.assertEqual(self.queue.peek_next("gestion_cuenta").client_name, "Ana")
        self.assertEqual(self.queue.peek_next("gestion_cuenta").client_name, "Ana")
        self.assertEqual(self.queue.stats()["gestion_cuenta"], 1)

    def test_peek_next_on_empty_queue_raises(self):
        with self.assertRaises(EmptyQueueError):
            self.queue.peek_next("retiro")

    def test_call_and_peek_reject_invalid_service(self):
        with self.assertRaises(InvalidServiceTypeError):
            self.queue.call_next("hipoteca")
        with self.assertRaises(InvalidServiceTypeError):
            self.queue.peek_next("hipoteca")


class ListAndStatsTests(unittest.TestCase):
    def setUp(self):
        self.queue = BranchQueue()
        self.queue.issue_ticket("Ana", "deposito")
        self.queue.issue_ticket("Luis", "retiro")
        self.queue.issue_ticket("Eva", "deposito")

    def test_list_waiting_groups_by_service_in_order(self):
        waiting = self.queue.list_waiting()

        self.assertEqual(set(waiting), {"deposito", "retiro", "gestion_cuenta"})
        self.assertEqual([t.client_name for t in waiting["deposito"]], ["Ana", "Eva"])
        self.assertEqual([t.client_name for t in waiting["retiro"]], ["Luis"])
        self.assertEqual(waiting["gestion_cuenta"], [])

    def test_list_waiting_returns_a_copy(self):
        self.queue.list_waiting()["deposito"].clear()
        self.assertEqual(self.queue.stats()["deposito"], 2)

    def test_stats_counts_per_service_and_total(self):
        self.assertEqual(
            self.queue.stats(),
            {"deposito": 2, "retiro": 1, "gestion_cuenta": 0, "total": 3},
        )

    def test_stats_update_after_call_next(self):
        self.queue.call_next("deposito")
        stats = self.queue.stats()
        self.assertEqual(stats["deposito"], 1)
        self.assertEqual(stats["total"], 2)


class CLITests(unittest.TestCase):
    def run_cli(self, inputs):
        """Ejecuta el menú con entradas simuladas y devuelve (cola, salida)."""
        queue = BranchQueue()
        output = io.StringIO()
        with patch("builtins.input", side_effect=inputs), redirect_stdout(output):
            BranchQueueCLI(queue).run()
        return queue, output.getvalue()

    def test_issue_ticket_by_number_and_exit(self):
        queue, output = self.run_cli(["1", "Ana", "2", "6"])

        self.assertIn("Ticket emitido", output)
        self.assertEqual(queue.stats()["retiro"], 1)

    def test_invalid_menu_option_does_not_crash(self):
        _, output = self.run_cli(["9", "abc", "6"])
        self.assertIn("Opción no válida", output)

    def test_invalid_service_is_reported(self):
        queue, output = self.run_cli(["1", "Ana", "hipoteca", "6"])

        self.assertIn("Tipo de servicio inválido", output)
        self.assertEqual(queue.stats()["total"], 0)

    def test_call_next_on_empty_queue_is_reported(self):
        _, output = self.run_cli(["2", "1", "6"])
        self.assertIn("No hay clientes esperando", output)

    def test_end_of_input_exits_cleanly(self):
        _, output = self.run_cli(EOFError())
        self.assertIn("Hasta luego", output)


if __name__ == "__main__":
    unittest.main()
