import os
import time
import random
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

app = FastAPI(title="IA SPORT - Motor y Simulador")

# Configuración de CORS para permitir que tu frontend en localhost:3000 haga peticiones
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. LÓGICA DEL SIMULADOR
# ==========================================
def ejecutar_simulacion(match_id: int, iteraciones: int = 10):
    print(f"Iniciando simulación para el partido {match_id}...")
    
    # Cuotas base iniciales
    cuotas_actuales = {
        "1x2_home": 2.15, "1x2_draw": 3.40, "1x2_away": 3.80,
        "corners_over": 9.50, "cards_over": 4.50, "goals_over": 2.50
    }

    for i in range(iteraciones):
        time.sleep(2) # Espera 2 segundos entre actualizaciones
        mercado = random.choice(list(cuotas_actuales.keys()))
        
        variacion = random.uniform(-0.05, 0.05)
        nueva_cuota = round(cuotas_actuales[mercado] * (1 + variacion), 2)
        
        if nueva_cuota < 1.01:
            nueva_cuota = 1.01
            
        cuotas_actuales[mercado] = nueva_cuota
        
        # Separamos el mercado de la selección
        if "1x2" in mercado:
            market_db = "1x2"
            selection_db = mercado.split("_")[1]
        else:
            market_db = mercado.split("_")[0]
            selection_db = "over"
            
        odds_data = {
            "match_id": match_id,
            "market": market_db,
            "selection": selection_db,
            "price": nueva_cuota
        }
        
        try:
            supabase.table("odds").insert(odds_data).execute()
            print(f"[Tick {i+1}] {mercado} movido a: {nueva_cuota}")
        except Exception as e:
            print(f"Error insertando: {e}")
            
    print("Simulación terminada.")

@app.post("/simular/{match_id}")
def iniciar_simulacion(match_id: int, background_tasks: BackgroundTasks):
    # Ejecuta la simulación en segundo plano para no bloquear la API
    background_tasks.add_task(ejecutar_simulacion, match_id, 10)
    return {"mensaje": f"Simulación iniciada para el partido {match_id}"}

# ==========================================
# 2. LÓGICA DEL MOTOR DE ANÁLISIS
# ==========================================
@app.get("/analisis/{match_id}")
def obtener_analisis(match_id: int):
    # Buscamos todas las cuotas del partido
    response = supabase.table("odds") \
        .select("*") \
        .eq("match_id", match_id) \
        .order("recorded_at", desc=False) \
        .execute()
        
    if not response.data:
        raise HTTPException(status_code=404, detail="No hay cuotas para este partido")

    mercados = {}
    for row in response.data:
        clave = f"{row['market']}_{row['selection']}"
        if clave not in mercados:
            mercados[clave] = []
        mercados[clave].append(row['price'])

    resultado = {}

    for clave, precios in mercados.items():
        if len(precios) < 2:
            resultado[clave] = {"estado": "neutral", "confianza": 50.0, "tendencia": 0.0}
            continue

        precio_inicial = precios[0]
        precio_actual = precios[-1]
        variacion = ((precio_actual - precio_inicial) / precio_inicial) * 100

        if variacion > 2.0:
            estado = "alcista"
            confianza = min(100.0, 50.0 + abs(variacion) * 5)
        elif variacion < -2.0:
            estado = "bajista"
            confianza = min(100.0, 50.0 + abs(variacion) * 5)
        else:
            estado = "neutral"
            confianza = 50.0

        resultado[clave] = {
            "estado": estado,
            "confianza": round(confianza, 2),
            "tendencia_porcentual": round(variacion, 2),
            "cuota_inicial": precio_inicial,
            "cuota_actual": precio_actual
        }

    return {
        "match_id": match_id,
        "analisis": resultado
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)