# Simulación de 1.000 semanas de Receivables Copilot (27-oct-2026)

**Pregunta:** ¿cobra mejor el agente que los recordatorios de calendario fijo de PayPal?
Código: `app/simulacion.py` (hipótesis y efectos verdaderos escritos antes de ejecutar), gráfica en `app/graficas.py`, resultados en `app/resultados/`. 6 pruebas en `app/tests/test_simulacion.py`.

## Cómo se ha hecho
- **1.000 semanas sintéticas:** un estudio con algo de caja, unas nóminas dentro de 7 días y 3-5 facturas abiertas de 30 clientes, cada uno con una probabilidad verdadera de pagar a tiempo que nadie ve
- **Respuestas de los clientes:** un 8 % disputa la factura; otros confirman el pago o piden más tiempo, y lo que dicen se parece a lo que de verdad harán
- **Efectos verdaderos, iguales para todos y algo más flojos de lo que supone la política** (para no jugar en casa):
  - Un recordatorio multiplica las probabilidades de pagar a tiempo por 1,4 (la política supone 1,5)
  - Un descuento del 2 %, por 2,5 (la política supone 3)
  - Una factura en disputa solo se paga en la semana un 5 % de las veces
- **Mismas semanas y la misma suerte para los 5 agentes:**
  1. Copilot
  2. Copilot sin leer las respuestas
  3. Recordatorios fijos de PayPal
  4. Descuento a todos
  5. No hacer nada
- **Coste por semana:** descuentos dados + 3 $ por recordatorio + 1.500 $ cada vez que falta dinero para las nóminas

## Resultados
| Semilla 2030 (fijada de antemano) | Semanas cortas el día de las nóminas | Coste por semana | Recordatorios por semana | Semanas presionando a quien disputa | Semanas presionando a quien confirmó |
|---|---|---|---|---|---|
| **Receivables Copilot** | **19,8 %** | **373 $** | **0,71** | **0** | **0** |
| Copilot sin leer respuestas | 19,1 % | 363 $ | 1,35 | 205 | 452 |
| Recordatorios fijos de PayPal | 20,6 % | 319 $ | 3,46 | 277 | 608 |
| Descuento a todos | 17,6 % | 529 $ | 0 | 319 | 655 |
| No hacer nada | 22,2 % | 333 $ | 0 | 0 | 0 |

| Hipótesis | Semilla 2030 | Semilla 2031 |
|---|---|---|
| H1. Menos semanas cortas que los recordatorios fijos | ❌ −0,8 puntos (IC −1,8 a +0,2): no se distingue del azar | ❌ −1,0 (IC −2,1 a +0,1) |
| H2. Menos recordatorios que el calendario fijo | ✅ −2,75 por semana (un 80 % menos) | ✅ −2,61 |
| H3. Más barato que dar descuento a todos | ✅ −155 $ por semana | ✅ −122 $ |
| H4. Nunca presiona a quien disputa; sin leer las respuestas, sí | ✅ 0 frente a 205 semanas | ✅ 0 frente a 205 |

## Qué significa, sin adornos
**Lo bueno:**
- **Molesta mucho menos:** un 80 % menos de recordatorios que el calendario fijo
- **Nunca presiona a un cliente que disputa la factura ni a uno que ya ha confirmado el pago.** El calendario fijo de PayPal lo hace en 277 y 608 semanas de cada 1.000; el mismo agente sin leer las respuestas, en 205 y 452. Esto lo aporta la capa de IA
- Es más barato que dar descuento a todos

**Lo malo (no se puede vender como «cobra mejor»):**
1. **No evita más nóminas impagadas que los recordatorios fijos.** La diferencia (−0,8 y −1,0 puntos) cabe en el azar en las dos semillas
2. **Cuesta más que los recordatorios fijos** (373 $ frente a 319 $) **e incluso que no hacer nada** (333 $). Gasta unos 74 $ por semana en descuentos que no cambian lo bastante el resultado
3. Leer las respuestas no reduce las semanas cortas (19,8 % frente a 19,1 %): el agente deja de presionar a quien confirmó o disputa, que es lo correcto con los clientes, pero eso no trae más dinero

**Causa probable (sin comprobar todavía):** muchas semanas ningún plan cumple el 5 % de riesgo (sin hacer nada, se queda corto un 22 %). En esas semanas el motor elige el plan más seguro, cueste lo que cueste, y reparte descuentos que no salvan las nóminas. Además, supone que los descuentos funcionan algo mejor de lo que funcionan.

## Segunda tanda (27-oct, noche): el arreglo del coste, con el sí del candidato
**El cambio** (motor común, `ReceivablesPolicy.if_unsafe = "cheapest"`): cuando ningún plan deja el riesgo por debajo del 5 %, se elige el de menor coste esperado (descuentos + recordatorios + 1.500 $ × probabilidad de quedarse corto), en vez del más seguro a cualquier precio. Hipótesis fijadas antes de medir, semillas nuevas 2032 y 2033. La regla antigua sigue como agente de comparación.

| Semilla 2032 | Semanas cortas | Coste por semana | Recordatorios por semana | Presionando a quien disputa |
|---|---|---|---|---|
| **Copilot (arreglado)** | **17,0 %** | **298 $** | **1,34** | **0** |
| Copilot sin leer respuestas | 16,8 % | 306 $ | 1,93 | 181 |
| Recordatorios fijos de PayPal | 17,6 % | 274 $ | 3,47 | 249 |
| Descuento a todos | 15,1 % | 492 $ | 0 | 286 |
| No hacer nada | 19,3 % | 290 $ | 0 | 0 |
| Copilot, regla antigua | 15,9 % | 335 $ | 0,73 | 0 |

| Hipótesis | Semilla 2032 | Semilla 2033 |
|---|---|---|
| H5. Más barato que los recordatorios fijos | ❌ +23 $ por semana (IC +12 a +34) | ❌ +7 $ (IC −6 a +20): no se distingue |
| H6. No más de 1 punto por encima en semanas cortas | ✅ −0,6 (IC −1,3 a +0,1) | ✅ −1,3 (IC −2,2 a −0,4): **aquí, mejor de forma clara** |
| H7. Mantiene menos recordatorios y nunca presiona a quien disputa | ✅ un 61 % menos | ✅ |
| H8. La demo no cambia | ✅ (pruebas) | ✅ |

- **Frente a la regla antigua:** unos 36 $ menos por semana (con un intervalo claro), a cambio de ~1 punto más de semanas cortas. Contando la penalización de 1.500 $, sale mejor. Por eso se queda como regla por defecto
- **En resumen:**
  - **Igual de seguro que los recordatorios fijos de PayPal** el día de las nóminas (en una semilla, incluso mejor)
  - **Un 61 % menos de recordatorios**
  - **Nunca presiona a quien disputa o ya confirmó**
  - Cuesta lo mismo o un poco más (de +7 a +23 $ por semana)
  - **No se puede decir que sea más barato**

## Para el vídeo (en inglés, lo que sí se puede decir)
> "Across 1,000 simulated weeks, Receivables Copilot kept payroll as safe as PayPal's fixed reminder schedule while sending 61% fewer reminders, and it never chased a customer who was disputing an invoice or had already confirmed payment. The fixed schedule chased a disputing customer in about a quarter of the weeks."

## Tercera tanda (28-oct): un fallo de la simulación y un agente que aprende de sus resultados
**Lo que encontró el diagnóstico** (`app/diagnostico_descuentos.py`, solo con las semillas ya usadas 2030 y 2031):
- **El agente se creía más seguro de lo que era.** Preveía de media un 8-10 % de riesgo de quedarse sin dinero el día de las nóminas, y le pasaba en el 20-23 % de las semanas. Por eso creía que con un descuento ya bajaba del 5 %: dos tercios de lo gastado en descuentos se iban en semanas que creía «seguras» y no lo eran
- **Fallo de nuestra simulación:** las respuestas de los clientes se sorteaban aparte de lo que luego hacían, así que no avisaban de nada (aunque el texto del simulador decía que sí). Las tandas 1 y 2 lo tenían: «leer las respuestas no ayuda» salía en parte de ahí
- **Fallo pequeño del agente:** no restaba el 2 % del descuento del dinero que esperaba cobrar. Arreglado en el motor común; la demo no cambia

**El cambio** (`motor_comun/triage_core/collections_calibration.py`): el agente guarda, de cada factura, la probabilidad que creía, si estaba vencida, qué hizo y si el cliente pagó a tiempo. Cada 20 semanas ajusta una regresión logística pequeña, que empieza en lo que supone la política y solo se mueve lo que dicen los datos. Corrige su previsión, lo que resta estar vencida, lo que suman un recordatorio y un descuento, y cuánto fiarse de cada tipo de respuesta. La regla de decisión no cambia. «Copilot, no learning» es el motor de la tanda 2, para comparar.

**Desarrollo (semillas ya usadas 2030 y 2031, no cuentan como prueba):**
- Primer intento: acertaba su riesgo, pero aprendió que los recordatorios no sirven (×1,0) y dejó de mandarlos. Causa: solo recordaba a quien no había confirmado, que paga peor de lo que creía, y la culpa se la llevaba el recordatorio. Arreglo: aprender también cuánto fiarse de cada tipo de respuesta
- Con el arreglo: riesgo previsto 16,5 % y real 16,9 % (semilla 2030); 21,1 % y 21,0 % (2031). Sin aprender: 9,4 % y 16,3 %; 10,9 % y 20,8 %
- Lo que aprende se parece a lo que de verdad pasa en el simulador: estar vencida ×0,21-0,22; recordatorio ×1,22-1,26; descuento ×1,64-1,79; una confirmación vale ×4-5 más de lo que suponía la política
- Frente a los recordatorios fijos: coste +5 $ y +10 $ por semana (los dos IC incluyen el 0); semanas cortas −0,4 y −1,5 puntos (la segunda, clara)
- Sin el tope del 5 % («solo coste»): −3 $ y −1 $ por semana frente a los fijos, dentro del azar. El tope no explica todo el coste

**Hipótesis fijadas antes de ejecutar las semillas nuevas 2034 y 2035** (también en `app/simulacion.py`, `HIPOTESIS_TANDA3`):
- **H9.** Con aprendizaje, el riesgo medio que prevé Copilot queda a menos de 2 puntos del real; sin aprender, a más de 5
- **H10.** Copilot no se queda corto más que los recordatorios fijos (IC 95 % de la diferencia por debajo de +1 punto)
- **H11.** Leer las respuestas ya ayuda: Copilot cuesta menos que el mismo motor sin leerlas (IC por debajo de 0)
- **H12.** Copilot cuesta menos que los recordatorios fijos (IC por debajo de 0)
- **H13.** «Solo coste» (sin el tope del 5 %) cuesta menos que los recordatorios fijos (IC por debajo de 0)
- **H14.** Se mantienen H2 y H4: menos recordatorios que el calendario fijo y nunca presiona a quien disputa
- **H15.** La historia de la demo no cambia (pruebas de `app/tests/test_escenario.py`)

### Resultados de la tercera tanda (semillas nuevas 2034 y 2035, 28-oct)
| Semilla 2034 | Semanas cortas | Coste por semana | Recordatorios por semana | Presionando a quien disputa | Riesgo que preveía |
|---|---|---|---|---|---|
| **Receivables Copilot (aprende)** | **23,7 %** | **388 $** | **1,16** | **0** | 19,2 % |
| Copilot sin leer respuestas | 24,4 % | 405 $ | 1,53 | 187 | 17,2 % |
| Copilot sin aprender (tanda 2) | 22,9 % | 385 $ | 1,27 | 0 | 12,2 % |
| Copilot «solo coste» (sin el tope del 5 %) | 23,6 % | 379 $ | 1,28 | 0 | 19,2 % |
| Recordatorios fijos de PayPal | 24,9 % | 384 $ | 3,48 | 280 | — |
| Descuento a todos | 22,0 % | 587 $ | 0 | 306 | — |
| No hacer nada | 26,8 % | 402 $ | 0 | 0 | — |

En la semilla 2035: Copilot 26,5 % de semanas cortas y 432 $; los fijos, 28,5 % y 438 $; sin hacer nada, 31,2 %.

| Hipótesis | Semilla 2034 | Semilla 2035 |
|---|---|---|
| H9. Prevé su riesgo a menos de 2 puntos (sin aprender, a más de 5) | ❌ a 4,5 puntos (sin aprender, a 10,7) | ❌ a 4,6 (sin aprender, a 10,2) |
| H10. No se queda corto más que los fijos | ✅ **−1,2 puntos** (IC −2,0 a −0,4) | ✅ **−2,0** (IC −3,0 a −1,0) |
| H11. Leer las respuestas abarata | ✅ −17 $ por semana (IC −29 a −6) | ✅ −14 $ (IC −25 a −3) |
| H12. Más barato que los fijos | ❌ +4 $ (IC −8 a +16) | ❌ −6 $ (IC −20 a +7) |
| H13. «Solo coste» más barato que los fijos | ❌ −5 $ (IC −16 a +6) | ❌ −9 $ (IC −22 a +4) |
| H14. Menos recordatorios y nunca presiona a quien disputa | ✅ un 67 % menos | ✅ un 57 % menos |
| H15. La demo no cambia | ✅ (pruebas) | ✅ |

**Lo que aprende el agente** (semilla 2034, 3.632 facturas): estar vencida ×0,24, recordatorio ×1,19, descuento ×1,92, una confirmación ×3,3 más de lo que suponía la política y una petición de más tiempo ×0,48.

**Qué significa, sin adornos:**
- **Ahora sí se queda sin dinero menos veces que los recordatorios fijos de PayPal**, y de forma clara en las dos semillas nuevas (1,2 y 2,0 puntos menos). Antes solo era «igual de seguro»
- **Con un 62 % menos de recordatorios**, y sin presionar nunca a quien disputa (los fijos lo hacen en 280 y 231 semanas de cada 1.000) ni a quien ya confirmó (458 y 441)
- **Leer las respuestas ya sirve:** 14-17 $ menos por semana que el mismo motor sin leerlas. En las tandas 1 y 2 no se veía por el fallo del simulador
- **El autocontrol reduce a menos de la mitad el error de su previsión** (de unos 10 puntos a unos 4,5), pero no llega a los 2 puntos que nos pusimos como objetivo (H9 no se cumple)
- **Sigue sin ser más barato:** cuesta lo mismo que los recordatorios fijos (de 6 $ menos a 4 $ más por semana, dentro del azar), también sin el tope del 5 %
- **Frente al motor sin aprender:** el coste es parecido (+3 $ y −11 $) y se queda corto algo más a menudo en una semilla (+0,8 puntos, IC +0,2 a +1,4). Lo que aporta aprender es saber cuánto riesgo corre de verdad, no ahorrar

### Para el vídeo (en inglés, lo que sí se puede decir; sustituido por la versión de la quinta tanda)
> "We tested it on a thousand simulated weeks against a fixed reminder schedule. It ran short on payday less often, with sixty-two percent fewer reminders, and it never chased a customer who was disputing or had already confirmed payment. The fixed schedule chased someone who was disputing in about a quarter of the weeks. And the agent checks itself: it compares what it predicted with what happened, and corrects its forecast."

**No decir:** «más barato» ni «sabe exactamente cuánto riesgo corre» (se desvía unos 4,5 puntos).

## Cuarta tanda (28-oct, noche): el autocontrol aprende también de las disputas
**El problema (H9):** el agente preveía menos riesgo del que corría (4,5 puntos en las semillas 2034 y 2035).

**Diagnóstico** con semillas ya usadas (`app/diagnostico_riesgo.py`). Riesgo de quedarse corto, previsto / real:
| Semilla | Todas las semanas | Semanas con alguna disputa | Semanas sin disputa | Facturas en disputa: llega antes de las nóminas, creído / real |
|---|---|---|---|---|
| 2030 | 16,5 / 16,9 | 18,9 / 23,1 | 15,6 / 14,5 | 66,8 % / 39,7 % |
| 2031 | 21,1 / 21,0 | 23,7 / 29,9 | 20,1 / 17,7 | 54,2 % / 35,8 % |
| 2034 | 19,2 / 23,7 | 23,6 / 32,0 | 17,3 / 20,0 | 53,5 % / 38,6 % |
| 2035 | 21,9 / 26,5 | 25,1 / 36,9 | 20,7 / 22,6 | 60,0 % / 29,6 % |

- **En las semillas de desarrollo, la cifra global cuadraba por casualidad:** se quedaba corto en las semanas con disputa y se pasaba en las demás, y los dos errores se anulaban
- **La causa principal:** el autocontrol dejaba fuera las facturas en disputa. El agente creía que llegaban antes de las nóminas en el 54-67 % de los casos y llegaban en el 30-40 %
- Las facturas sin disputa se prevén bien (a 1-3 puntos en cada grupo: vencidas o no, y por acción)

**El cambio:** el autocontrol aprende también de las facturas en disputa (cuánto bajan de verdad las probabilidades). Con las semillas de desarrollo, la previsión de las disputas pasa a 44,7 % frente a 39,7 % y 37,2 % frente a 35,8 %.

**Hipótesis** fijadas antes de medir, semillas nuevas 2036 y 2037 (`HIPOTESIS_TANDA4` en `app/simulacion.py`):
| Hipótesis | Semilla 2036 | Semilla 2037 |
|---|---|---|
| H16. El riesgo previsto, a menos de 2 puntos del real | ❌ 23,2 % frente a 21,2 % (2,0 puntos, se pasa) | ❌ 16,5 % frente a 23,9 % (7,4 puntos, se queda corto) |
| H17. Menos desvío que el Copilot de la tanda 3 | ❌ 2,0 frente a 1,0 | ✅ 7,4 frente a 9,1 |
| H18. No se queda corto más que los fijos | ✅ −1,9 puntos (IC −2,8 a −1,0) | ✅ −1,5 (IC −2,4 a −0,6) |
| H19. Más barato que los fijos | ❌ −2 $ (IC −16 a +11) | ❌ +1 $ (IC −12 a +14) |
| H20. Menos recordatorios y nunca presiona a quien disputa | ✅ | ✅ |

| | 2036 | 2037 |
|---|---|---|
| Copilot: corto / coste por semana | 21,2 % / 355 $ | 23,9 % / 392 $ |
| Copilot de la tanda 3 (sin las disputas) | 21,1 % / 354 $ | 24,2 % / 395 $ |
| Recordatorios fijos | 23,1 % / 357 $ | 25,4 % / 391 $ |
| Lo que aprende de una disputa (además del ×0,2 de la política) | ×0,26 | ×0,10 |

**Qué significa:** las disputas ya se prevén bien, pero **las decisiones no cambian** (mismo coste y mismas semanas cortas que sin el cambio) y **el riesgo de la semana sigue desviado**, sobre todo en la 2037. Los errores pequeños de cada factura se suman en la cola: acertar con cada factura no basta. De ahí la quinta tanda.

## Quinta tanda (28-oct, noche): el agente revisa también su riesgo semanal
**El cambio:** cada semana guarda la probabilidad de quedarse corto que preveía para el plan elegido y si se quedó corto. Cada 20 semanas ajusta con eso una corrección de dos números (`collections_calibration.fit_risk`) y la aplica al riesgo de todos los planes que compara. Solo usa semanas pasadas. La demo no cambia: el estudio no tiene semanas pasadas.

**Hipótesis** (`HIPOTESIS_TANDA5` en `app/simulacion.py`), fijadas antes de ejecutar las semillas nuevas 2038 y 2039. El criterio de «cuadra» cambia: con 1.000 semanas, lo que pasa de verdad ya tiene un margen de ±2,6 puntos, así que se pide que el IC 95 % de la diferencia incluya el 0.

**Comprobación con la semilla ya usada 2037** (la del desvío de 7,4 puntos): prevé un 24,7 % y se queda corto el 23,9 % (+0,8; IC −1,6 a +3,2). Sin la revisión, −7,4.

| Hipótesis | Semilla 2038 | Semilla 2039 |
|---|---|---|
| H21. El riesgo previsto cuadra con el real (el IC incluye el 0) | ❌ +3,5 puntos (IC +1,1 a +5,8): prudente de más | ✅ 0,0 (IC −2,4 a +2,4) |
| H22. Menos desvío que sin la revisión | ✅ 3,5 frente a 3,9 | ✅ 0,0 frente a 0,3 |
| H23. No se queda corto más que los fijos | ✅ −2,2 puntos (IC −3,2 a −1,2) | ✅ −2,4 (IC −3,4 a −1,4) |
| H24. Más barato que sin la revisión | ❌ −3 $ (IC −11 a +5) | ✅ −27 $ (IC −38 a −15) |
| H25. Menos recordatorios y nunca presiona a quien disputa | ✅ | ✅ |
| H12. Más barato que los fijos (se vuelve a medir) | ❌ −9 $ (IC −23 a +6) | ❌ +2 $ (IC −13 a +17) |

| | Semilla 2038 | Semilla 2039 |
|---|---|---|
| Copilot: corto / coste / recordatorios por semana | 22,0 % / 365 $ / 1,65 | 24,7 % / 419 $ / 1,61 |
| Copilot sin la revisión (el de la tanda 4) | 21,3 % / 368 $ / 1,52 | 25,1 % / 445 $ / 0,03 |
| Recordatorios fijos | 24,2 % / 373 $ / 3,39 | 27,1 % / 417 $ / 3,47 |
| Riesgo previsto / real: Copilot | 25,5 % / 22,0 % | 24,7 % / 24,7 % |
| Riesgo previsto / real: sin aprender | 12,0 % / 22,1 % | 15,5 % / 24,4 % |
| Semanas en que los fijos presionan a quien disputa / a quien confirmó | 252 / 455 | 238 / 464 |

**Qué significa, sin adornos:**
- **La revisión semanal arregla los desvíos grandes:** en la 2037 pasa de 7,4 puntos a 0,8. En las semillas nuevas, el Copilot de la tanda 4 ya no iba tan desviado, así que se nota poco (de 3,9 a 3,5 y de 0,3 a 0,0)
- En la 2038 se queda del lado prudente (prevé 3,5 puntos más de riesgo del que corre) y se queda corto 0,7 puntos más que sin la revisión (IC +0,2 a +1,2)
- **Frente a los recordatorios fijos:** se queda corto menos veces (2,2 y 2,4 puntos, claros), con la mitad de recordatorios y sin presionar nunca a quien disputa o ya confirmó. **Sigue sin ser más barato** (de 9 $ menos a 2 $ más por semana, dentro del azar)
- Leer las respuestas ya no ahorra dinero claro (−10 $ y +5 $), pero sí semanas cortas (2,4 y 1,9 puntos menos)
- En la 2039, el Copilot sin la revisión casi dejó de mandar recordatorios (0,03 por semana) y gastó más en descuentos; con la revisión, 27 $ menos por semana

### Para el vídeo (en inglés, versión de la quinta tanda; sustituida por la de la sexta)
> "We tested it on a thousand simulated weeks against a fixed reminder schedule. It ran short on payday less often, with about half the reminders, and it never chased a customer who was disputing or had already confirmed payment. The fixed schedule chased someone who was disputing in about a quarter of the weeks. And the agent checks itself: it compares what it predicted with what happened, invoice by invoice and week by week, and corrects its forecast."

**No decir:** «más barato» ni «sabe exactamente cuánto riesgo corre».

## Sexta tanda (28-oct, noche): el historial de cada cliente crece
**El cambio:** cada factura que el cliente paga por sí mismo (sin recordatorio ni descuento, sin disputa y sin estar ya vencida) entra en su historial 5 semanas después, cuando ya han llegado hasta las tardías. Antes el historial se quedaba fijo y el autocontrol solo corregía errores de todos a la vez. Es lo que más mejoró la previsión de Airwallex.

**Comprobación con la semilla ya usada 2038:** el Copilot con el historial fijo da exactamente lo de la quinta tanda (22,0 % y 365 $). Con el historial que crece: error con cada cliente 10,8 puntos frente a 12,2; riesgo previsto +1,9 frente a +3,5; mismo coste.

**Hipótesis** (`HIPOTESIS_TANDA6` en `app/simulacion.py`), semillas nuevas 2040 y 2041:
| Hipótesis | Semilla 2040 | Semilla 2041 |
|---|---|---|
| H26. Conoce mejor a cada cliente que con el historial fijo | ✅ 8,5 puntos frente a 9,1 | ❌ 7,5 frente a 7,2 |
| H27. Más barato que con el historial fijo | ❌ +2 $ (IC −4 a +9) | ✅ −13,5 $ (IC −21 a −6) |
| H28. Más barato que los recordatorios fijos | ❌ −3,5 $ (IC −15 a +8) | ❌ −3,5 $ (IC −12 a +5) |
| H29. El riesgo previsto cuadra con el real | ✅ −0,5 puntos (IC −2,8 a +1,7) | ✅ +0,7 (IC −1,5 a +2,9) |
| H30. Menos recordatorios y nunca presiona a quien disputa | ✅ | ✅ |
| H1. Menos semanas cortas que los fijos | ✅ −1,3 (IC −2,1 a −0,5) | ❌ −0,4 (IC −1,0 a +0,2) |

| | Semilla 2040 | Semilla 2041 |
|---|---|---|
| Copilot: corto / coste / recordatorios por semana | 19,4 % / 317 $ / 1,32 | 19,7 % / 308 $ / 1,27 |
| Copilot con el historial fijo (tanda 5) | 18,9 % / 315 $ / 1,51 | 20,3 % / 322 $ / 0,07 |
| Recordatorios fijos | 20,7 % / 321 $ / 3,41 | 20,1 % / 312 $ / 3,46 |
| Riesgo previsto / real: Copilot | 18,9 % / 19,4 % | 20,4 % / 19,7 % |
| Riesgo previsto / real: sin aprender | 13,4 % / 18,5 % | 8,4 % / 18,6 % |

**Qué significa:** el historial que crece no cambia mucho las decisiones. Ayuda en una semilla y no en la otra. En la 2041, el Copilot con el historial fijo casi dejó de mandar recordatorios (0,07 por semana), como ya pasó en la 2039: lo que aprende del efecto de un recordatorio a veces se tuerce, y con el historial que crece no pasó. Lo más sólido: **el riesgo que prevé cuadra con el real en las dos semillas** (a menos de 1 punto).

## El techo (28-oct, noche): ¿cuánto ganaría un agente que supiera la verdad?
`app/techo_oraculo.py` (no cuenta como prueba; semillas ya medidas). El «oráculo» sabe la probabilidad verdadera de cada cliente, el efecto real de cada acción, lo que resta estar vencida, cómo se reparten los retrasos y con qué probabilidad responde cada cliente. Lee las respuestas y decide con la misma regla que Copilot. Solo no sabe la suerte de la semana.

| Semilla | Oráculo: corto / coste | Copilot: corto / coste | Fijos: corto / coste | Oráculo - fijos (coste) |
|---|---|---|---|---|
| 2038 | 21,3 % / 351 $ | 22,0 % / 365 $ | 24,2 % / 373 $ | −22,6 $ (IC −38 a −7) |
| 2040 | 18,5 % / 310 $ | 19,4 % / 317 $ | 20,7 % / 321 $ | −10,8 $ (IC −24 a +3) |
| 2041 | 18,8 % / 304 $ | 19,7 % / 308 $ | 20,1 % / 312 $ | −7,7 $ (IC −19 a +3) |

**Qué significa, sin adornos:**
- **Ni sabiendo la verdad se gana mucho frente a los recordatorios fijos:** de 8 a 23 $ por semana, y en dos de tres semillas ni siquiera es claro. La mayoría de las semanas cortas no las salva ningún recordatorio ni descuento
- Copilot se queda entre los fijos y el techo: recoge entre un tercio y la mitad de lo que se puede ganar
- **Para dejar de perseguir el coste:** «no es más barato» es sobre todo un límite del escenario, no de la previsión. Donde Copilot sí gana claro es en molestar menos (un tercio de los recordatorios), no presionar a quien disputa o ya confirmó, y saber cuánto riesgo corre

### Para el vídeo (en inglés, versión de la sexta tanda)
> "We tested it on a thousand simulated weeks against a fixed reminder schedule. It ran short on payday less often, with a third of the reminders, and it never chased a customer who was disputing or had already confirmed payment. The fixed schedule chased someone who was disputing in about a quarter of the weeks. And the agent checks itself: it compares what it predicted with what happened, invoice by invoice and week by week, and corrects its forecast."

**No decir:** «más barato». «Ran short less often» vale: menos en las ocho semillas nuevas, claro en siete.
