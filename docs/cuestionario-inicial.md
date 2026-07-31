# Cuestionario inicial

El contenido del cuestionario: qué se pregunta, con qué palabras y qué opciones
tiene cada respuesta. El **porqué** de cada decisión está en `diseno-dominio.md`
(3.15 a 3.19); aquí está el **qué**.

Los valores de las opciones van en inglés porque acaban siendo constantes del
código, como `ACTIVITY_LEVELS` o `COOKING_METHODS`. Las etiquetas van en español
porque las lee el usuario.

**Todo son opciones cerradas salvo una pregunta**, marcada como tal.

---

## Lo que el marco legal impone al cuestionario

Tras la consulta legal, esto se sostiene sobre cuatro condiciones, y dos afectan
directamente a este documento:

- Es una **herramienta de planificación de menús para población sana**, presentada
  como bienestar y educación alimentaria, **no como tratamiento**.
- Hay que **declarar de forma clara y visible que los planes los genera una IA**
  (art. 50 del Reglamento de IA, exigible desde el 2 de agosto de 2026).

Las otras dos —los valores nutricionales salen de mi base de datos y no del
modelo, e información precontractual y desistimiento conformes al TRLGDCU— ya
están cubiertas en el diseño o son de la parte comercial.

Esto tiene tres consecuencias concretas:

**1. El cribado va primero, no en medio.** Si la aplicación es para población
sana, lo primero que hay que averiguar es si esta persona lo es. Y hay una razón
de protección de datos además de la legal: **si voy a derivarla a un profesional,
no tiene sentido haberle pedido antes el peso, los perímetros y las alergias.**
Preguntar y salir es recoger el mínimo imprescindible.

**2. Del cribado no guardo el detalle.** Guardar "este usuario tiene diabetes" es
un dato de salud de categoría especial que no necesito para nada. Guardo
únicamente que pasó el cribado y cuándo (`screening_passed_at`). La respuesta
concreta no se persiste.

**3. El vocabulario de toda la aplicación es ahora un artefacto legal.** No digo
*dieta*, *pauta*, *prescripción* ni *tratamiento*. Digo **plan de comidas**,
**menú semanal**, **sugerencia**. No es cosmética: es lo que sostiene que esto no
es un acto sanitario.

---

## Bloque 0 · Cribado

**Va antes que cualquier otra pregunta.** Pantalla única.

> **Antes de empezar**
>
> Esta herramienta organiza menús para personas sanas. No sustituye a un
> profesional sanitario y no está pensada para tratar ninguna enfermedad.
>
> ¿Te encuentras en alguna de estas situaciones?

Selección múltiple. Valores: `diabetes`, `kidney_liver`, `pregnancy_lactation`,
`eating_disorder`, `cardiovascular`, `professional_diet`, `none`.

| Etiqueta |
|---|
| Diabetes (tipo 1 o tipo 2) |
| Enfermedad renal o hepática |
| Embarazo o lactancia |
| Un trastorno de la conducta alimentaria, diagnosticado o en tratamiento |
| Enfermedad cardiovascular con alimentación pautada por un médico |
| Sigo una pauta de alimentación indicada por un profesional sanitario |
| Ninguna de las anteriores |

**Si marca cualquiera menos la última**, no se continúa:

> Con lo que me has contado, tu alimentación debería planificarla un
> dietista-nutricionista o tu médico, que pueden tener en cuenta cosas que esta
> herramienta no ve.
>
> No voy a generarte un plan, y prefiero decírtelo ahora que darte algo que no te
> conviene.

Sin botón de "continuar igualmente". Si alguien quiere mentir, volverá atrás y
cambiará la respuesta; eso ya no está en mi mano. Lo que sí está es no ponérselo
delante.

**Si marca "ninguna"**: se guarda `screening_passed_at` con la fecha y sigue.

---

## Bloque 1 · Quién eres

Ya existe casi entero en `users`.

**Sexo** — `male` · `female` · `other` → Hombre · Mujer · Otro
**Fecha de nacimiento** — selector de fecha. Se guarda la fecha, la edad se
calcula (3.5).
**Altura** en cm · **Peso** en kg.

**¿Cómo es tu día a día?** — `ACTIVITY_LEVELS`

| Valor | Etiqueta |
|---|---|
| `sedentary` | Paso el día sentado y no hago ejercicio |
| `light` | Camino algo o entreno una o dos veces por semana |
| `moderate` | Entreno tres o cuatro veces por semana |
| `high` | Entreno casi a diario o mi trabajo es físico |

Preguntado por conducta y no por etiqueta: "moderado" significa cosas distintas
para cada persona.

**Perímetros** (cintura, cadera, cuello) — opcionales, en ajustes. No los pido en
el asistente: son los que más gente abandona.

---

## Bloque 2 · Qué quieres conseguir

**Objetivo** — `GOALS`: `lose_fat` · `maintain` · `gain_muscle` → Perder grasa ·
Mantenerme · Ganar músculo

**¿A qué ritmo?** — **nuevo**, y de los que más cambian el resultado.

| Valor | Etiqueta |
|---|---|
| `gentle` | Sin prisa, que apenas se note en el día a día |
| `moderate` | Un ritmo sostenible |
| `fast` | Quiero ver cambios pronto, aunque cueste más seguirlo |

> **Juanma:** las cifras que hay detrás de cada ritmo son tuyas. Yo he puesto tres
> niveles porque tres se entienden y cinco no, pero si en Ciencias del Deporte
> manejáis otra escala, cámbiala. Y valora si `fast` debe existir: es el que más
> gente abandona y el que peor imagen da si alguien lo lleva al límite.

---

## Bloque 3 · Lo que no puedes comer

**Alergias** — selección múltiple sobre los **14 alérgenos de declaración
obligatoria** del anexo II del reglamento europeo de información alimentaria.

Usar esa lista y no una inventada tiene tres ventajas: es la que ya conoce la
gente de las etiquetas, es exhaustiva para lo que la ley considera relevante, y
me evita discutir qué entra. (Conviene que verifiques el listado vigente en la
fuente oficial antes de fijarlo en el código.)

Cereales con gluten · Crustáceos · Huevos · Pescado · Cacahuetes · Soja · Leche ·
Frutos de cáscara · Apio · Mostaza · Sésamo · Sulfitos · Altramuces · Moluscos

**Una alergia marcada quita esos alimentos del catálogo antes de que el modelo lo
vea** (3.17). No se le pide al modelo que tenga cuidado.

**Intolerancias** — lista aparte, porque tienen dosis y no exclusión.

`lactose` · `gluten_non_celiac` · `fructose` · `sorbitol` · `histamine`

Y para cada una, cuánto tolera:

| Valor | Etiqueta |
|---|---|
| `none` | Nada, ni cantidades pequeñas |
| `small` | Cantidades pequeñas sí |
| `moderate` | Bastante, solo me sienta mal en exceso |

> **Juanma:** la celiaquía no es una intolerancia, es una enfermedad autoinmune y
> la exclusión es absoluta. Va con las alergias (cereales con gluten), no aquí.
> Revísame esta lista, que es tuya.

**Alimentos que no quieres ver** — buscador contra el catálogo, **no un campo de
texto**. La persona escribe para buscar, pero **guarda identificadores de
alimento**, no lo que tecleó. Así el filtro es una consulta y no hay texto libre
llegando al prompt.

**Preferencia alimentaria** — `FOOD_PREFERENCES`: `omnivore` · `vegetarian` ·
`vegan` → Como de todo · Vegetariana · Vegana

---

## Bloque 4 · Cómo comes

**¿Cuántas veces comes al día?** — un número, de 1 a 10.

Lo intenté como selección múltiple de momentos con nombre (desayuno, media
mañana, comida, merienda, cena) y **no vale**: hay quien come ocho veces al día y
ahí no hay cinco casillas que marcar. El número es la respuesta honesta.

Lo que sí es fijo son **tres anclas: desayuno, comida y cena.** Todo lo demás se
reparte entre ellas. Esa es la estructura, no una lista de cinco nombres.

**No pregunto a qué hora come.** Es una pantalla entera para un dato que el
usuario contesta a ojo y que casi no cambia el plan.

**¿Postre?** — `none` · `lunch` · `dinner` · `both`
→ No · Después de comer · Después de cenar · En las dos

**¿El fin de semana comes distinto?** — `same` · `looser` · `very_different`
→ Igual que entre semana · Algo más relajado · Bastante distinto

Esta importa más de lo que parece: un plan que finge que el sábado es igual que
el martes se rompe el sábado.

---

## Bloque 5 · Cómo cocinas

**¿Qué tienes en la cocina?** — selección múltiple sobre `COOKING_METHODS`, que
ya existe. **Esto filtra de verdad**: si no marca horno, no aparecen recetas al
horno.

`raw` Crudo · `boiled` Cocido · `steamed` Al vapor · `microwaved` Microondas ·
`griddled` A la plancha · `sauteed` Salteado · `baked` Al horno ·
`air_fried` Freidora de aire · `fried` Frito · `stewed` Guisado

Más, en la misma pantalla: **congelador** (sí/no). Va aquí y no en la compra,
porque es equipamiento.

**¿Cuánto tiempo tienes para cocinar entre semana?**

| Valor | Etiqueta |
|---|---|
| `quick` | Quince minutos como mucho |
| `normal` | Media hora |
| `relaxed` | Una hora o más, me gusta cocinar |

---

## Bloque 6 · La compra

**¿Cada cuánto compras?** — `daily` · `twice_week` · `weekly` · `biweekly`
→ Casi a diario · Dos o tres veces por semana · Una vez por semana · Cada dos
semanas

Decide cuánto producto fresco puede haber en el plan.

**¿Con qué presupuesto?**

| Valor | Etiqueta |
|---|---|
| `tight` | Ajustado, busco lo económico |
| `normal` | Sin agobios, pero sin excesos |
| `generous` | El precio no es lo que me preocupa |

Bandas y no euros: una cifra depende de cuánta gente coma en casa y de dónde
vivas, y me obligaría a mantener una conversión que no aporta nada al modelo.

---

## Bloque 7 · Gustos

**Todo este bloque va en ajustes menos la última pregunta.** Son matices que se
contestan mejor con una parrilla delante, y ninguno impide generar el primer plan.

**¿Picante?** — `none` · `mild` · `love_it`
→ Nada · Un poco · Cuanto más mejor

**¿Cuánta variedad quieres?** — la que sustituye a mi constante `MIN_RECIPES`
(3.22).

| Valor | Etiqueta |
|---|---|
| `low` | Prefiero repetir platos, me simplifica la vida |
| `balanced` | Un equilibrio |
| `high` | Cuanta más variedad, mejor |

**¿Y en el desayuno?** — `same_every_day` · `varied`
→ Me vale el mismo todos los días · Prefiero variar

Separada a propósito: mucha gente quiere el mismo desayuno siempre y cenas
distintas. Una sola respuesta global obliga a acertar mal en uno de los dos
sitios, y es exactamente lo que hacía que `gpt-4o-mini` pareciera peor de lo que
era.

**¿Tomas alguna de estas a diario?** — selección múltiple: café · leche o bebida
vegetal · refrescos · alcohol. Suman y la gente se olvida de declararlas.

**¿Pesas la comida?** — `weighs` · `estimates`
→ Sí, uso báscula · No, calculo a ojo

Si contesta `estimates`, darle "127 g de pollo" es teatro: el plan tiene que salir
en cantidades redondas y medidas caseras (una rebanada, un puñado, un filete
mediano).

---

## Bloque 8 · Entrenamiento

**En el asistente inicial**, no en ajustes. Es mi terreno y es lo que puede
diferenciar esto de un generador de menús cualquiera: la actividad física cambia
las necesidades, y preguntarla al final o no preguntarla es renunciar a la ventaja
que tengo.

**¿Entrenas?** — `no` · `strength` · `cardio` · `mixed` · `sport`
→ No · Fuerza · Cardio · Mixto · Practico un deporte

**¿Cuántos días por semana?** — 1 a 7. Solo si la anterior no es `no`.

En ajustes, para quien quiera afinar: qué días concretos, a qué hora entrena, y si
quiere comer distinto los días de entrenamiento.

---

## Bloque 9 · La única pregunta abierta

> **¿Has intentado antes cambiar tu alimentación? ¿Qué te hizo dejarlo?**
>
> Cuéntamelo con tus palabras. Esto no lo lee nadie más que la aplicación, y es lo
> que más ayuda a que el plan no repita lo que ya no te funcionó.

Opcional, y **la única entrada libre de todo el cuestionario**. Tratada como
hostil por defecto según 3.19: límite de longitud, delimitada en el prompt como
dato del usuario y nunca mezclada con las instrucciones, escapada al pintarla y
parametrizada en la base de datos.

---

## El reparto: asistente inicial y ajustes

**En el asistente** (nueve pantallas; las de selección múltiple se contestan a
toques y van rápido):

1. Cribado
2. Sexo, fecha de nacimiento, altura, peso
3. Actividad
4. Objetivo y ritmo
5. Alergias, intolerancias y preferencia alimentaria
6. Cuántas veces comes al día
7. Qué tienes en la cocina y cuánto tiempo
8. Compra y presupuesto
9. Entrenamiento: si entrenas, de qué tipo y cuántos días

**En ajustes, después**: alimentos que no quieres ver, postre, fin de semana,
picante, variedad, si el desayuno puede repetirse, bebidas diarias, si pesas la
comida, perímetros, los detalles del entrenamiento y la pregunta abierta.

El criterio es que **el usuario vea su primer plan cuanto antes**. Todo lo demás
se contesta mejor con una parrilla delante que en abstracto, y lo que de verdad va
a personalizar esto no es el formulario: es qué comidas rechaza y cambia después.

---

## Lo que hay que enseñar en pantalla, no en el cuestionario

Consecuencia directa del art. 50 y del encuadre de "no es tratamiento". Va en el
producto desde el primer día, no cuando se cobre:

- **En cada plan, visible y no en letra pequeña**: que lo ha generado una
  inteligencia artificial.
- **Que no sustituye a un profesional sanitario.**
- **De dónde salen los números** (USDA FoodData Central) y que el modelo elige
  alimentos y cantidades, pero no inventa valores nutricionales. Además de ser
  cierto, es un argumento de confianza.
- **El aviso de `incomplete_nutrients`** cuando algún alimento no tenga un dato:
  un total que parece completo sin serlo es peor que un aviso.

---

## Lo que necesito que revises

Lo técnico lo defiendo; lo de nutrición y entrenamiento es tuyo:

- **Los tres ritmos del objetivo** y si `fast` debe existir.
- **La lista de intolerancias** y sus tres niveles de tolerancia.
- **Si falta alguna alergia relevante** fuera de las 14 obligatorias.
- **Las franjas horarias** de cada comida.
- **El bloque de entrenamiento**: es el que más flojo va, porque es donde menos sé
  y donde tú más puedes aportar.
