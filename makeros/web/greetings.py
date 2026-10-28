"""Greeting shown on the home hero, rotated by day-of-year.

One per day, cycling through 30 lab-flavored hellos (tech, maker and
plain silly). English code, Spanish greetings.
"""

from __future__ import annotations

from datetime import date

GREETINGS = [
    "Hola, {name}. El laboratorio está a una temperatura óptima.",
    "Boot completo. Buenos días, {name}.",
    "Buenas, {name}. Cuidado con el cable suelto.",
    "Hola, {name}. Hoy sí se calibra la impresora.",
    "Saludos, {name}. Tu sesión fue compilada sin warnings.",
    "Hola, {name}. El soldador está caliente y la ideas también.",
    "Buen día, {name}. Recordá: medir dos veces, cortar una.",
    "Hola, {name}. El servidor durmió bien, gracias por preguntar.",
    "Buenas, {name}. Cero errores en el registro de hoy… por ahora.",
    "Hola, {name}. Que el filamento fluya a tu favor.",
    "Ping recibido, {name}. Latencia humana: aceptable.",
    "Hola, {name}. Bienvenido de nuevo a la matriz del laboratorio.",
    "Buen día, {name}. Hoy es un buen día para prototipar.",
    "Hola, {name}. La gravedad sigue funcionando; el láser también.",
    "Saludos, {name}. Nivel de café del sistema: por verificar.",
    "Hola, {name}. Cargando entusiasmo… 100%.",
    "Buenas, {name}. El kanban necesita amor.",
    "Hola, {name}. Confía en el proceso, y en el multímetro.",
    "Buen día, {name}. Estás dentro del rango de tolerancia.",
    "Hola, {name}. Se detectaron buenas ideas en tu vecindad.",
    "Hola, {name}. Los tornillos M3 te extrañaron.",
    "Buenas, {name}. Sistema de ventanas: abierto. Herramientas: listas.",
    "Hola, {name}. Commit inicial del día: hacer algo grande.",
    "Saludos, {name}. La resistencia es fútil; el acrílico se corta igual.",
    "Hola, {name}. Hoy el láser está de buen humor.",
    "Buen día, {name}. Documentá antes de que se te olvide.",
    "Hola, {name}. Toda gran fabricación empieza con un café.",
    "Buenas, {name}. El grafo de la wiki crece mientras no miras.",
    "Hola, {name}. Mantené las manos fuera del área de corte.",
    "Saludos, {name}. Estado del laboratorio: listo para lo que sea.",
]


def greeting_for(name: str, today: date | None = None) -> str:
    today = today or date.today()
    return GREETINGS[today.timetuple().tm_yday % len(GREETINGS)].format(name=name)
