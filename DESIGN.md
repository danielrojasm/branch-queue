# Notas de diseño — Branch Queue

## 1. ¿Por qué una cola por tipo de servicio?

`BranchQueue` guarda un diccionario `{tipo_de_servicio: deque}`. Cada agente solo trabaja con la cola de su servicio.

**Con una única lista compartida**, todos los clientes están mezclados en orden de llegada. Para atender al siguiente cliente de `deposito`, el agente tiene que recorrer la lista desde el principio, saltándose a todos los clientes de `retiro` y `gestion_cuenta`, hasta encontrar el primero de su servicio. Después hay que sacarlo de en medio de la lista, lo que obliga a desplazar los elementos que vienen detrás. Las dos cosas cuestan **O(n)**, donde *n* es el total de personas en la sala. Cuanto más llena está la sucursal, más tarda cada llamada, aunque solo haya una persona esperando para depósitos.

**Con una cola por servicio**:

- Buscar la cola es **O(1)** (búsqueda en diccionario).
- El siguiente cliente siempre está al principio de esa cola, así que no hay que buscarlo.
- `deque.popleft()` saca ese primer elemento en **O(1)**, mientras que `list.pop(0)` cuesta O(n).
- Para emitir un ticket se usa `append` sobre la cola correcta, que también es **O(1)**.

Así, `call_next` y `peek_next` tardan lo mismo haya 3 o 3 000 personas esperando para otros servicios. Además, el orden FIFO dentro de cada servicio se mantiene sin esfuerzo: como los tickets se añaden siempre al final y se sacan siempre del principio, cada cola queda ordenada por llegada.

El contador de tickets (`_next_number`) es **uno solo para todo el sistema** y no uno por cola. Por eso dos clientes nunca tienen el mismo número, aunque estén esperando servicios distintos.

## 2. Dos agentes del mismo servicio llaman a `call_next` a la vez

Pensemos que `call_next` funcionara en dos pasos separados: *leer* el primero de la cola y luego *eliminarlo*:

```
Agente A: lee queue[0]   -> Ticket #7
Agente B: lee queue[0]   -> Ticket #7   (A todavía no lo ha eliminado)
Agente A: elimina queue[0]   (sale el #7)
Agente B: elimina queue[0]   (sale el #8, ¡que nadie ha llamado!)
```

Esto es una **condición de carrera**. Los dos agentes llaman al cliente #7, y el #8 sale de la cola sin que nadie lo atienda, así que se pierde.

**La mutación que tiene que ocurrir primero es sacar el ticket de la cola.** Leer el ticket y quitarlo de la cola tiene que ser **una sola operación atómica**, y solo después de eso se le asigna el ticket al agente. Una vez que un agente ha sacado el ticket, ningún otro puede verlo ni llamarlo.

En esta implementación, `call_next` hace exactamente eso con `queue.popleft()`, que extrae y devuelve el elemento en una sola operación. En CPython, `append` y `popleft` de `deque` son seguros entre hilos (thread-safe). Aun así, `call_next` primero comprueba si la cola está vacía y luego llama a `popleft`, y esas dos instrucciones juntas no son atómicas. Si hay concurrencia real (hilos, varios quioscos, un servidor), se necesita una de estas opciones:

- proteger cada cola con un `threading.Lock` (un candado por servicio, para que los agentes de servicios distintos no se bloqueen entre sí), o
- llamar a `popleft()` directamente y capturar el `IndexError` si la cola está vacía, en lugar de comprobar antes y extraer después, o
- en un sistema distribuido, usar una operación atómica del almacén de datos (por ejemplo `LPOP` en Redis, o `SELECT … FOR UPDATE SKIP LOCKED` / `DELETE … RETURNING` en SQL).

La regla es la misma en todos los casos: **primero se saca el ticket de la cola de forma atómica, y después se usa**. Nunca se lee el ticket primero para sacarlo después.
