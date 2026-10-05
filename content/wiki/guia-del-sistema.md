---
title: "Guía del sistema"
tags: [guia, makeros]
---

# Guía del sistema

MakerOS es una capa delgada sobre un árbol de Markdown. Nada de lo que
escribas aquí queda atrapado en una base de datos: si la app muere, los
archivos siguen siendo la fuente de verdad.

## Cómo se organiza el contenido

```
content/
  projects/<slug>/project.md
  tasks/<slug>.md
  events/<slug>.md
  people/<name>.md
  research/<slug>.md
  exhibits/cauce/devices/<device>.md
  inventory/<item>.md
  wiki/<path>.md
```

## Cómo crear una página

1. Crea un archivo `.md` bajo `content/wiki/`.
2. Ponle frontmatter con `title` y opcionalmente `tags`.
3. Escribe Markdown normal. Usa `[[otra-pagina]]` para enlazar páginas
   del wiki o `[[pagina|texto visible]]` para poner etiqueta.
4. Guarda. En segundos aparece en el índice y en la búsqueda.

## Reglas del laboratorio

- **Contraseñas nunca en Markdown.** Van a la bóveda (fase 4).
  En las páginas se referencia el *nombre* del elemento de la bóveda.
- Los nombres de archivo son los slugs: minúsculas, guiones, sin espacios.
- Todo lo que sea narrativa va en Markdown; lo relacional va en frontmatter.
