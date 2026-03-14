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

## Los 5 objetivos del benchmark (idénticos para cada tier)

OBJETIVO 1 — Mandelbrot mínimo y correcto:
"Implementar src/python/mandelbrot.py.
Función: render_mandelbrot(w=1080, h=1920, max_iter=256) -> np.ndarray
Usar SOLO aritmética numpy — cero loops Python.
Guardar output/mandelbrot.png.
Medir con tracemalloc: peak RAM debe ser <500MB.
Medir con time.perf_counter: tiempo de render.
Guardar métricas en benchmarks/results.json:
{model_tier, function, lines_of_code, cpu_seconds, memory_peak_mb,
 uses_vectorization: bool, tests_passed: bool}
Test: dimensiones correctas + PNG válido + RAM <500MB.
Después de guardar el PNG, evaluar similitud visual:
    from src.python.ssim_scorer import score_against_reference
    result = score_against_reference('output/mandelbrot.png')
    print(f'SSIM: {result}')
Incluir en FINAL_REPORT: 'ssim_score': result['score'], 'ssim_quality': result['quality']"

OBJETIVO 2 — Julia set con colormap matemático:
"Implementar src/python/julia.py.
Función: render_julia(c=(-0.7+0.27j), w=1080, h=1920) -> np.ndarray
Colormap HSV implementado desde cero en numpy (sin matplotlib).
Sin loops Python — todo vectorizado.
Añadir métricas a benchmarks/results.json.
Test: imagen no es negra (variance > 1000) + dimensiones + RAM.
Después de guardar el PNG, evaluar similitud visual:
    from src.python.ssim_scorer import score_against_reference
    result = score_against_reference('output/julia.png')
    print(f'SSIM: {result}')
Incluir en FINAL_REPORT: 'ssim_score': result['score'], 'ssim_quality': result['quality']"

OBJETIVO 3 — Perlin noise 2D desde cero:
"Implementar src/python/perlin.py.
Ken Perlin's original algorithm — sin librerías de noise.
Función: generate_perlin(w=1080, h=1920, octaves=6) -> np.ndarray
Optimizar para numpy: usar meshgrid, no doble loop.
Comparar: medir tiempo con loop puro vs implementación vectorizada.
Documentar speedup en benchmarks/results.json.
Test: variance > 500 + suavidad (no pixelado).
Después de guardar el PNG, evaluar similitud visual:
    from src.python.ssim_scorer import score_against_reference
    result = score_against_reference('output/perlin.png')
    print(f'SSIM: {result}')
Incluir en FINAL_REPORT: 'ssim_score': result['score'], 'ssim_quality': result['quality']"

OBJETIVO 4 — Kernel C++ con ctypes:
"Implementar src/cpp/mandelbrot.cpp.
Función C: void render_mandelbrot_c(float* out, int w, int h, int max_iter)
Compilar: gcc -O3 -march=native -shared -fPIC -o src/cpp/libmandelbrot.so
Wrapper Python: src/python/mandelbrot_cpp.py via ctypes.
Medir speedup vs implementación Python pura.
Target: ≥5x speedup.
Si el modelo usa SIMD intrinsics (SSE/AVX) → bonus metric: simd_used=true
Documentar en benchmarks/results.json."

OBJETIVO 5 — Compositor final <500MB:
"Implementar src/python/compositor.py.
Combinar los 3 renderers en una sola imagen usando streaming por tiles:
  - Procesar la imagen en tiles de 1080×192 (10 tiles verticales)
  - Cada tile: mandelbrot(tile) * 0.4 + julia(tile) * 0.4 + perlin(tile) * 0.2
  - Liberar memoria del tile antes del siguiente
  - RAM máxima en cualquier momento: <500MB
Guardar output/composite_final.png (1080×1920).
Medir RAM peak de todo el proceso.
Test: PNG válido + RAM <500MB durante toda la ejecución.
Después de guardar el PNG, evaluar similitud visual:
    from src.python.ssim_scorer import score_against_reference
    result = score_against_reference('output/composite_final.png')
    print(f'SSIM: {result}')
Incluir en FINAL_REPORT: 'ssim_score': result['score'], 'ssim_quality': result['quality']"

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
