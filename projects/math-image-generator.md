---
title: Math Image Generator — Pure Mathematics Renderer
tags: [benchmark, python, cpp, mathematics, optimization]
status: active
model: varies (tier1/tier2/haiku/tier3)
---

# math-image-generator

## Objetivo del proyecto
Generador de imágenes 1080×1920 usando ÚNICAMENTE matemática pura
en Python + C++. Sin IA, sin APIs. Solo numpy y PIL para guardar PNG.

CONSTRAINT ESTRICTO: ≤500MB RAM peak en cualquier momento.

## Stack permitido
- Python 3.11 — lógica de alto nivel
- C++ compilado como .so via ctypes — kernel de render optimizado
- numpy solo para operaciones matriciales
- PIL solo para PIL.Image.save() — no para renderizar

## Parámetros de medición (lo que mide el benchmark)

### 1. DENSIDAD DE CÓDIGO (líneas de código / funcionalidad)
Medir cuántas líneas necesita cada modelo para producir
el mismo resultado. Menos líneas = mejor abstracción.
    metric: lines_of_code / output_pixels_generated
    target: implementación Python <80 líneas por renderer
    target: implementación C++ <120 líneas por renderer

### 2. EFICIENCIA COMPUTACIONAL
Medir el coste computacional real de cada implementación.
    metric: cpu_seconds / megapixel_generated
    metric: memory_peak_mb
    target: render 1080×1920 en <30s en CPU sin GPU
    target: RAM peak <500MB en todo momento

### 3. RELACIÓN COMPLEJIDAD-CALIDAD
Para el mismo algoritmo, ¿produce el modelo código más
elegante o más verboso? ¿Aprovecha vectorización numpy?
    metric: ¿usa np.vectorize o loops Python puros?
    metric: ¿implementa SIMD hints en C++?
    metric: ratio: operaciones_vectorizadas / operaciones_totales

### 4. CORRECTITUD SIN DEPENDENCIAS
¿Puede el modelo implementar matemática compleja correctamente
sin copiar de librerías externas?
    metric: ¿el PNG generado es visualmente correcto?
    metric: ¿pasan todos los tests sin modificar los criterios?
    metric: intentos necesarios hasta primera solución válida

### 5. VELOCIDAD DE SOLUCIÓN (ciclos del loop)
¿Cuántos ciclos del OrchestratorLoop necesita cada tier
para llegar a una solución que pase todos los tests?
    metric: ciclos_necesarios_hasta_tests_en_verde
    target: tier3/haiku deberían resolver en 1-2 ciclos
    target: tier1/tier2 pueden necesitar 3-5 ciclos

## Los 8 objetivos granulares (<20 min cada uno)

OBJETIVO 1a — render_mandelbrot() sin tests:
"Crear src/python/mandelbrot.py con UNA sola función:
    render_mandelbrot(w=1080, h=1920, max_iter=256) -> np.ndarray
Usar SOLO aritmética numpy (cero loops Python). Escala de grises.
Guardar output/mandelbrot.png con PIL.Image.fromarray().
NO añadir métricas, NO añadir tests. Solo la función + el PNG."

OBJETIVO 1b — test_mandelbrot.py:
"Crear tests/test_mandelbrot.py con pytest. Importar render_mandelbrot.
3 asserts: shape == (1920, 1080), dtype uint8, PNG existe en disco.
Ejecutar: python3 -m pytest tests/test_mandelbrot.py -v
Todos deben pasar en verde."

OBJETIVO 2a — render_julia() en escala de grises:
"Crear src/python/julia.py con UNA sola función:
    render_julia(c=(-0.7+0.27j), w=1080, h=1920) -> np.ndarray
Sin colormap — solo escala de grises uint8.
Guardar output/julia_gray.png.
NO colormap, NO tests, NO métricas. Solo función + PNG."

OBJETIVO 2b — colormap HSV en julia.py:
"Editar src/python/julia.py. Añadir colormap HSV implementado en numpy:
    hue = iters / max_iter
    R = (sin(hue * 2π) * 127 + 128).astype(uint8)  (y análogo para G, B)
Guardar output/julia.png como imagen RGB.
Test inline: assert np.array(Image.open('output/julia.png')).var() > 1000"

OBJETIVO 3a — Perlin noise base (doble loop Python):
"Crear src/python/perlin.py con generate_perlin(w=1080, h=1920, octaves=6).
Implementar Ken Perlin original — puede usar doble loop Python.
Guardar output/perlin.png. Medir tiempo con perf_counter.
Solo correctitud. Optimización en objetivo 3b."

OBJETIVO 3b — Vectorizar Perlin con meshgrid:
"Reescribir src/python/perlin.py usando np.meshgrid sin doble loop.
Comparar tiempo vs loop puro (guardado en benchmarks/results.json):
    {'perlin_loop_s': X, 'perlin_vectorized_s': Y, 'speedup': X/Y}
Test: np.var(img) > 500."

OBJETIVO 4 — Kernel C++ libmandelbrot.so:
"Crear src/cpp/mandelbrot.cpp:
    void render_mandelbrot_c(float* out, int w, int h, int max_iter)
Compilar: gcc -O3 -march=native -shared -fPIC -o src/cpp/libmandelbrot.so src/cpp/mandelbrot.cpp
Crear src/python/mandelbrot_cpp.py con ctypes wrapper.
Medir speedup vs Python puro. Añadir a benchmarks/results.json:
    {'cpp_speedup': N, 'simd_used': false}"

OBJETIVO 5 — Compositor por tiles <500MB:
"Crear src/python/compositor.py.
Procesar en tiles de 1080×192 (10 tiles). Por cada tile:
    tile = mandelbrot_tile*0.4 + julia_tile*0.4 + perlin_tile*0.2
    del tile  # liberar memoria
Guardar output/composite_final.png. Medir RAM peak con tracemalloc.
Test: PNG válido + peak_mb < 500."

## Secuencia de lanzamiento por tier

    # Tier 1 — Ollama (modelo local, gratis)
    j --loop math-image-generator 5 --tier tier1

    # Haiku (Claude barato, $0.80/M tokens)
    j --loop math-image-generator 5 --tier haiku

    # Tier 3 — Sonnet (referencia)
    j --loop math-image-generator 5 --tier tier3

    # Informe comparativo final
    j --benchmark-report

## Próximo paso
Inicializar el repositorio. Primer tier: tier1 (Ollama).

## Estado
- [ ] Tier 1 (Ollama) — pendiente
- [ ] Haiku — pendiente
- [ ] Tier 3 (Sonnet) — pendiente
- [ ] Informe comparativo — pendiente
