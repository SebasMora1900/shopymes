
# Importaciones necesarias
from flask import Flask, render_template, request, session, redirect, url_for, flash, send_from_directory, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from openai import OpenAI
from requests_oauthlib import OAuth2Session
from requests.exceptions import ConnectionError
import requests
from flask import session

# ============================================================================
# CONFIGURACIÓN DEL SERVIDOR Y LA BASE DE DATOS
# ============================================================================

app = Flask(__name__)
# Es crucial usar una clave secreta segura para las sesiones
# Idealmente, esta clave se cargaría desde una variable de entorno
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_super_segura_456')

# Configuración de la conexión a la base de datos MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '' # Si tienes una contraseña, colócala aquí
app.config['MYSQL_DB'] = 'shopymes' # Nombre de la base de datos corregido
app.config['MYSQL_CURSORCLASS'] = 'DictCursor' # Devuelve los resultados como diccionarios
mysql = MySQL(app)

# ============================================================================
# CONFIGURACIÓN DE OPENAI CHAT API
# ============================================================================
# IMPORTANTE: Reemplaza "TU_API_KEY_AQUI" con tu clave real.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "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")
client = OpenAI(
    api_key="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"
)


# ============================================================================
# CONFIGURACIÓN DE GOOGLE OAUTH

# ============================================================================

# Cargar las credenciales de Google desde variables de entorno para mayor seguridad
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "408081647545-1kvbnbdu7l2ge69hcbj0ebg5n4kace7j.apps.googleusercontent.com")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "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")
REDIRECT_URI = "http://localhost:5000/google_callback"

# Endpoints de Google para la autenticación
AUTHORIZATION_BASE_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"

# Scopes (permisos) que solicitamos a Google
SCOPES = ["https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile", "openid"]

# ============================================================================
# FUNCIONES DE LA BASE DE DATOS (Mejoradas con consultas preparadas)
# ============================================================================

def get_db_cursor():
    """Devuelve un cursor de la base de datos."""
    conn = mysql.connection
    return conn.cursor()

def is_logged_in():
    """Verifica si un usuario ha iniciado sesión."""
    return 'logged_in' in session and session['logged_in']
@app.route('/admin/administrar_tiendas')
def administrar_tiendas():
    if not is_logged_in() or session.get('rol') != 'emprendedor':
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM tienda WHERE dueño = %s", (session['correo'],))
    tiendas_emprendedor = cur.fetchall()
    favoritos = session.get('favoritos', {'tiendas': [], 'productos': []})
    for t in tiendas_emprendedor:
        t['favorito'] = t['id'] in favoritos.get('tiendas', [])
    cur.close()
    return render_template('admin/administrar_tiendas.html', tiendas_emprendedor=tiendas_emprendedor)

def consulta_emprendedor_por_correo(correo):
    """Busca un emprendedor en la base de datos por su correo electrónico."""
    cursor = get_db_cursor()
    cursor.execute("SELECT nombre, correo, contraseña FROM emprendedores WHERE correo = %s", (correo,))
    emprendedor = cursor.fetchone()
    cursor.close()
    return emprendedor

def consulta_usuario_por_correo(correo):
    """Busca un usuario normal en la base de datos por su correo electrónico."""
    cursor = get_db_cursor()
    cursor.execute("SELECT nombre, correo, contraseña FROM clientes WHERE correo = %s", (correo,))
    usuario = cursor.fetchone()
    cursor.close()
    return usuario
    
def registrar_emprendedor_google(nombre, correo):
    """Registra un nuevo emprendedor con su cuenta de Google."""
    conn = mysql.connection
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO emprendedores (nombre, correo, contraseña) VALUES (%s, %s, %s)",
        (nombre, correo, 'oauth_google')
    )
    conn.commit()
    cursor.close()
    return cursor.lastrowid

def registrar_cliente_google(nombre, correo):
    """Registra un nuevo usuario normal con su cuenta de Google."""
    conn = mysql.connection
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO clientes (nombre, correo, contraseña) VALUES (%s, %s, %s)",
        (nombre, correo, 'oauth_google')
    )
    conn.commit()
    cursor.close()
    return cursor.lastrowid


def log_message(self, format, *args):
        """Log personalizado con timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {format % args}")
    
def end_headers(self):
        """Agregar headers CORS para desarrollo"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

def do_POST(self):
        """Maneja las peticiones POST para la API de chat"""
        if self.path == '/chat':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data)
                user_message = data.get('message', '')
                if not user_message:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'reply': 'No se recibió mensaje.'}).encode())
                    return
                
                # Llamar a la API de OpenAI con la nueva sintaxis
                try:
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": user_message}]
                    )
                    reply = response.choices[0].message.content.strip()
                except Exception as e:
                    reply = f"Error: {str(e)}"
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'reply': reply}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'reply': f'Error: {str(e)}'}).encode())
        else:
            super().do_POST()

# ============================================================================
# RUTAS DE LA APLICACIÓN
# ============================================================================

@app.route('/imagenes/<imagen>')
def imagenes(imagen):
    """
    Ruta para servir imágenes desde la carpeta de plantillas.
    Se usa una ruta absoluta para evitar problemas de directorio.
    """
    # Se utiliza app.root_path para obtener la ruta absoluta de la aplicación
    return send_from_directory(os.path.join(app.root_path, 'templates', 'imagenes'), imagen)

@app.route('/')
def inicio():
    """Ruta de la página de inicio pública."""
    return render_template('sitio/index.html')
# Ruta para Contactanos
@app.route('/contactanos')
def contactanos():
    return render_template('sitio/contactanos.html')

# Ruta para Sobre Nosotros
@app.route('/sobre_nosotros')
def sobre_nosotros():
    return render_template('sitio/sobre_nosotros.html')
    
# Ruta para Soporte
@app.route('/soporte')
def soporte():
    return render_template('sitio/soporte.html')

# Ruta para Registro (elige rol o registro general)
@app.route('/registro')
def registro_general():
    return render_template('sitio/registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Maneja el inicio de sesión con usuario/contraseña."""
    session.pop('_flashes', None) # Limpiar todos los mensajes flash anteriores
    
    if request.method == 'POST':
        usuario = request.form['txtUsuario']
        contrasena = request.form['txtContrasena']

        # Intenta encontrar al usuario como un emprendedor
        emprendedor = consulta_emprendedor_por_correo(usuario)

        if emprendedor and check_password_hash(emprendedor['contraseña'], contrasena):
            session['logged_in'] = True
            session['rol'] = 'emprendedor'
            session['nombre'] = emprendedor['nombre']
            session['correo'] = emprendedor['correo']
            return redirect(url_for('admin_inicio'))
        
        # Si no es un emprendedor, intenta encontrarlo como un cliente
        cliente = consulta_usuario_por_correo(usuario)
        
        if cliente and check_password_hash(cliente['contraseña'], contrasena):
            session['logged_in'] = True
            session['rol'] = 'cliente'
            session['nombre'] = cliente['nombre']
            session['correo'] = cliente['correo']
            return redirect(url_for('admin_inicio'))
        
        flash("Usuario o contraseña incorrectos.")
        return render_template('sitio/login.html')
    
    return render_template('sitio/login.html')

@app.route('/registro_rol')
def registro_rol():
    """Ruta para elegir el rol antes de registrarse."""
    return render_template('sitio/registro_rol.html')

# ... código anterior ...
@app.route('/registro/<rol>', methods=['GET', 'POST'])
def registro(rol):
    """
    Ruta para el registro de nuevos usuarios, ahora con campos dinámicos.
    """
    if request.method == 'POST':
        email = request.form['txtEmail']
        contrasena = request.form['txtContrasena']
        repetir_contrasena = request.form['txtRepetirContrasena']
        
        # Validar si el correo ya está registrado en cualquiera de las dos tablas
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT correo FROM clientes WHERE correo = %s", (email,))
        cliente_existente = cursor.fetchone()
        cursor.execute("SELECT correo FROM emprendedores WHERE correo = %s", (email,))
        emprendedor_existente = cursor.fetchone()
        cursor.close()

        if cliente_existente or emprendedor_existente:
            flash('Este correo electrónico ya está registrado. Por favor, inicia sesión o usa otro correo.')
            return redirect(url_for('registro', rol=rol))
        
        if contrasena != repetir_contrasena:
            flash('Las contraseñas no coinciden.')
            return redirect(url_for('registro', rol=rol))

        if rol == 'cliente':
            nombre = request.form['txtNombre']
            if not nombre or not email or not contrasena:
                flash('Por favor, completa todos los campos.')
                return redirect(url_for('registro', rol=rol))
            
            hashed_password = generate_password_hash(contrasena)
            try:
                cursor = mysql.connection.cursor()
                cursor.execute("INSERT INTO clientes (nombre, correo, contraseña) VALUES (%s, %s, %s)",
                               (nombre, email, hashed_password))
                mysql.connection.commit()
                cursor.close()
                flash('Registro de cliente exitoso. ¡Ahora puedes iniciar sesión!', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                flash(f'Ocurrió un error al registrarse: {e}')
                return redirect(url_for('registro', rol=rol))

        elif rol == 'emprendedor':
            nombre_empresa = request.form['txtNombreEmpresa']
            sector = request.form['txtSector']
            cedula_judicial = request.form['txtCedulaJuridica']
            
            if not nombre_empresa or not email or not contrasena or not sector or not cedula_judicial:
                flash('Por favor, completa todos los campos.')
                return redirect(url_for('registro', rol=rol))

            hashed_password = generate_password_hash(contrasena)
            try:
                cursor = mysql.connection.cursor()
                cursor.execute("INSERT INTO emprendedores (nombre, correo, contraseña, sector, cedula_judicial) VALUES (%s, %s, %s, %s, %s)",
                               (nombre_empresa, email, hashed_password, sector, cedula_judicial))
                mysql.connection.commit()
                cursor.close()
                # Mensaje personalizado de confirmación de registro
                flash('¡Gracias por registrarte en ShopYmes! 🎉\nHemos recibido tu solicitud. Nuestro equipo verificará tu información en las próximas 24 horas. Te notificaremos por correo electrónico si tu empresa fue aprobada o si necesitamos información adicional.', 'success')
                return redirect(url_for('registro_confirmacion'))
            except Exception as e:
                flash(f'Ocurrió un error al registrarse: {e}')
                return redirect(url_for('registro', rol=rol))
    
    return render_template('sitio/registro.html', rol=rol)

@app.route('/google_login')
def google_login():
    """Inicia la sesión OAuth with Google."""
    google = OAuth2Session(GOOGLE_CLIENT_ID, scope=SCOPES, redirect_uri=REDIRECT_URI)
    authorization_url, state = google.authorization_url(
        AUTHORIZATION_BASE_URL,
        access_type="offline",
        prompt="select_account"
    )
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route('/google_callback')
def google_callback():
    """Maneja el callback de Google."""
    if 'oauth_state' not in session or session['oauth_state'] != request.args.get('state'):
        flash("Error de autenticación: estado no válido.")
        return redirect(url_for('login'))

    try:
        google = OAuth2Session(
            GOOGLE_CLIENT_ID,
            state=session['oauth_state'],
            redirect_uri=REDIRECT_URI
        )
        token = google.fetch_token(
            TOKEN_URL,
            client_secret=GOOGLE_CLIENT_SECRET,
            authorization_response=request.url
        )
        session['oauth_token'] = token
        
        user_info = requests.get(
            USERINFO_URL,
            headers={'Authorization': f'Bearer {token["access_token"]}'}
        ).json()
        
        user_email = user_info['email']
        user_name = user_info.get('name', user_info['email'])

        # Intenta encontrar al usuario en ambas tablas
        emprendedor = consulta_emprendedor_por_correo(user_email)
        cliente = consulta_usuario_por_correo(user_email)
        
        if emprendedor:
            session['logged_in'] = True
            session['rol'] = 'emprendedor'
            session['nombre'] = emprendedor['nombre']
            session['correo'] = emprendedor['correo']
            return redirect(url_for('admin_inicio'))
        
        elif cliente:
            session['logged_in'] = True
            session['rol'] = 'cliente'
            session['nombre'] = cliente['nombre']
            session['correo'] = cliente['correo']
            return redirect(url_for('admin_inicio'))

        # Si el usuario no existe, redirigirlo a una página donde escoja el rol.
        flash("Tu cuenta de Google no está registrada. Por favor, elige un rol para registrarte.")
        return redirect(url_for('google_registro_rol', nombre=user_name, correo=user_email))

    except ConnectionError as e:
        flash("Error de conexión con los servidores de Google. Por favor, inténtalo de nuevo más tarde.")
        return redirect(url_for('login'))
    except Exception as e:
        flash("Ha ocurrido un error durante la autenticación. Por favor, inténtalo de nuevo.")
        return redirect(url_for('login'))
        
@app.route('/google_registro_rol')
def google_registro_rol():
    """Muestra una página para que los usuarios de Google elijan su rol."""
    nombre = request.args.get('nombre')
    correo = request.args.get('correo')
    if not nombre or not correo:
        return redirect(url_for('login'))
    return render_template('sitio/google_registro_rol.html', nombre=nombre, correo=correo)
# ... (tus otras rutas) ...

# ... (código anterior) ...

# En tu archivo app.py
# ... (código anterior) ...

@app.route('/chat', methods=['POST'])
def chat():
    """
    Maneja las peticiones de chat para la API de OpenAI, con contexto dinámico.
    """
    try:
        data = request.json
        user_message = data.get('mensaje', '')
        tienda_id = data.get('tienda_id')
        
        if not user_message:
            return jsonify({'respuesta': 'No se recibió mensaje.'}), 400
        
        # Lógica para obtener el contexto de la tienda (si se proporciona)
        tienda_contexto = ""
        system_prompt = "Eres un asistente de ShopYmes, una plataforma de e-commerce para PYMES en Costa Rica. Tu objetivo es ayudar a los clientes a encontrar información sobre tiendas y productos. Responde de manera concisa y útil. No tienes información sobre eventos históricos, personas fuera de la plataforma o temas generales. Si la pregunta no está relacionada con el contexto, debes disculparte y pedir una pregunta relacionada con la tienda o la plataforma en general."

        if tienda_id:
            cur = mysql.connection.cursor()
            cur.execute("SELECT nombre_tienda, descripcion FROM tienda WHERE id = %s", (tienda_id,))
            tienda = cur.fetchone()
            
            cur.execute("SELECT nombre, descripcion, precio, unidad FROM productos WHERE tienda_id = %s", (tienda_id,))
            productos = cur.fetchall()
            cur.close()

            if tienda:
                tienda_contexto = f"El usuario está en la tienda llamada '{tienda['nombre_tienda']}'. Descripción de la tienda: '{tienda['descripcion']}'. "
                
                if productos:
                    productos_str = ", ".join([f"Producto: {p['nombre']} (Precio: {p['precio']}/{p['unidad']}) Descripción: {p['descripcion']}" for p in productos])
                    tienda_contexto += f"Los productos disponibles en esta tienda son: {productos_str}."

        # Construir el prompt para la IA con el contexto
        full_prompt = f"{system_prompt} {tienda_contexto}"
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": full_prompt},
                      {"role": "user", "content": user_message}]
        )
        
        reply = response.choices[0].message.content.strip()

        return jsonify({'respuesta': reply})

    except Exception as e:
        return jsonify({'respuesta': f'Lo siento, hubo un error al procesar tu mensaje: {str(e)}'}), 500
        
@app.route('/google_registro_finalizar', methods=['POST'])
def google_registro_finalizar():
    """Maneja el registro final después de la autenticación con Google."""
    nombre = request.form.get('nombre')
    correo = request.form.get('correo')
    rol = request.form.get('rol')
    
    if rol == 'emprendedor':
        registrar_emprendedor_google(nombre, correo)
        flash("Registro exitoso como emprendedor. Ahora puedes iniciar sesión con Google.")
    elif rol == 'cliente':
        registrar_cliente_google(nombre, correo)
        flash("Registro exitoso como cliente. Ahora puedes iniciar sesión con Google.")
    else:
        flash("Rol no válido.")
    
    return redirect(url_for('registro_confirmacion'))

@app.route('/registro_confirmacion')
def registro_confirmacion():
    return render_template('sitio/registro_confirmacion.html')

@app.route('/inicio')
def inicio_cliente():
    if not is_logged_in() or session.get('rol') != 'cliente':
        return redirect(url_for('login'))
    return render_template('sitio/inicio.html', nombre=session['nombre'])

@app.route('/admin/')
def admin_inicio():
    if not is_logged_in():
        return redirect(url_for('login'))

    tiendas_global = [] 
    tiendas_emprendedor = [] 
    cur = None

    favoritos = session.get('favoritos', {'tiendas': [], 'productos': []})

    try:
        cur = mysql.connection.cursor()
        
        # Función auxiliar para obtener tiendas con una vista previa de productos
        def obtener_tiendas_con_productos(query, params=None):
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            
            tiendas = cur.fetchall()
            for t in tiendas:
                t['favorito'] = t['id'] in favoritos.get('tiendas', [])
                # Agrega una consulta para obtener 2 productos de muestra
                cur.execute("SELECT imagen1, imagen2 FROM productos WHERE tienda_id = %s LIMIT 2", (t['id'],))
                t['productos_preview'] = cur.fetchall()
            return tiendas

        query_all_tiendas = "SELECT id, nombre_tienda, dueño, contactos, descripcion, logo, imagen1, imagen2 FROM tienda"
        tiendas_global = obtener_tiendas_con_productos(query_all_tiendas)

        if session.get('rol') == 'emprendedor':
            query_emprendedor = "SELECT id, nombre_tienda, dueño, contactos, descripcion, logo, imagen1, imagen2 FROM tienda WHERE dueño = %s"
            tiendas_emprendedor = obtener_tiendas_con_productos(query_emprendedor, (session['correo'],))
        
    except Exception as e:
        print(f"Error al obtener tiendas: {e}")
        flash('Ha ocurrido un error al cargar las tiendas. Por favor, inténtalo de nuevo más tarde.')

    finally:
        if cur:
            cur.close()

    return render_template('admin/index.html', 
                            nombre=session['nombre'], 
                            rol=session['rol'], 
                            tiendas_global=tiendas_global if tiendas_global else [],
                            tiendas_emprendedor=tiendas_emprendedor if tiendas_emprendedor else [],
                            favoritos=favoritos)

# Endpoint para chat OpenAI
@app.route('/api/chat_openai', methods=['POST'])
def api_chat_openai():
    data = request.get_json()
    message = data.get('message', '')
    if not message:
        return jsonify({'response': 'No se recibió mensaje.'}), 400
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": message}]
        )
        return jsonify({'response': response.choices[0].message.content})
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return jsonify({'response': f'Error: {str(e)}', 'detail': error_detail}), 500
# Ruta para registro de tienda
@app.route('/admin/registro_tienda', methods=['GET', 'POST'])
def registro_tienda():
    if not is_logged_in() or session.get('rol') != 'emprendedor':
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, nombre FROM categoria")
    categorias = cur.fetchall()
    if request.method == 'POST':
        nombre_tienda = request.form.get('nombre_tienda')
        nombre_dueño = request.form.get('nombre_dueño') 
        dueño = session['correo'] 
        contactos = request.form.get('contactos')
        descripcion = request.form.get('descripcion')
        categoria_id = request.form.get('categoria_id')
        logo = request.files.get('logo')
        imagen1 = request.files.get('imagen1')
        imagen2 = request.files.get('imagen2')
        cur.execute("SELECT 1 FROM tienda WHERE dueño = %s AND nombre_tienda = %s", (dueño, nombre_tienda))
        if cur.fetchone():
            cur.close()
            flash('Ya tienes una tienda con ese nombre.', 'danger')
            return render_template('admin/registro_tienda.html', categorias=categorias)
        if not (nombre_tienda and nombre_dueño and contactos and descripcion and categoria_id and logo and imagen1 and imagen2):
            flash('Todos los campos son obligatorios.', 'danger')
            return render_template('admin/registro_tienda.html', categorias=categorias)
        import os
        from werkzeug.utils import secure_filename
        upload_folder = os.path.join('static', 'tiendas')
        os.makedirs(upload_folder, exist_ok=True)
        logo_filename = secure_filename(logo.filename)
        imagen1_filename = secure_filename(imagen1.filename)
        imagen2_filename = secure_filename(imagen2.filename)
        logo.save(os.path.join(upload_folder, logo_filename))
        imagen1.save(os.path.join(upload_folder, imagen1_filename))
        imagen2.save(os.path.join(upload_folder, imagen2_filename))
        cur.execute("""
            INSERT INTO tienda (nombre_tienda, nombre_dueño, dueño, contactos, descripcion, categoria_id, logo, imagen1, imagen2)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            nombre_tienda, nombre_dueño, dueño, contactos, descripcion, categoria_id,
            f'/static/tiendas/{logo_filename}',
            f'/static/tiendas/{imagen1_filename}',
            f'/static/tiendas/{imagen2_filename}'
        ))
        mysql.connection.commit()
        cur.close()
        flash('¡Tienda registrada exitosamente!', 'success')
        return redirect(url_for('registro_tienda_exito'))
    return render_template('admin/registro_tienda.html', categorias=categorias)

@app.route('/admin/registro_tienda/exito')
def registro_tienda_exito():
    return render_template('admin/registro_tienda_exito.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente.')
    return redirect(url_for('inicio'))


# ===================== RUTA PARA AGREGAR Y VER PRODUCTOS DEL EMPRENDEDOR =====================
from werkzeug.utils import secure_filename

@app.route('/admin/productos_emprendedor', methods=['GET', 'POST'])
def productos_emprendedor():
    if not is_logged_in() or session.get('rol') != 'emprendedor':
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM tienda WHERE dueño = %s", (session['correo'],))
    tienda = cur.fetchone()

    if not tienda:
        cur.close()
        flash('Primero debes crear una tienda.')
        return redirect(url_for('admin_inicio'))

    correo_emprendedor = session['correo']
    mensaje = None

    if request.method == 'POST':
        # Asegúrate de que todas estas líneas tengan la misma sangría de 4 espacios
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        precio = request.form.get('precio')
        unidad = request.form.get('unidad')
        imagen1 = request.files.get('imagen1')
        imagen2 = request.files.get('imagen2')

        if not (nombre and descripcion and precio and unidad and imagen1 and imagen2):
            mensaje = 'Todos los campos son obligatorios.'
        else:
            upload_folder = os.path.join('static', 'tiendas')
            os.makedirs(upload_folder, exist_ok=True)
            imagen1_filename = secure_filename(imagen1.filename)
            imagen2_filename = secure_filename(imagen2.filename)
            imagen1.save(os.path.join(upload_folder, imagen1_filename))
            imagen2.save(os.path.join(upload_folder, imagen2_filename))

            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO productos (nombre, descripcion, precio, unidad, correo_emprendedor, imagen1, imagen2, tienda_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                nombre, descripcion, precio, unidad, correo_emprendedor,
                f'/static/tiendas/{imagen1_filename}',
                f'/static/tiendas/{imagen2_filename}',
                tienda['id']
            ))
            mysql.connection.commit()
            cur.close()
            mensaje = '¡Producto agregado exitosamente!'
    
    # Este bloque va fuera del 'if request.method == 'POST''
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM productos WHERE correo_emprendedor = %s", (correo_emprendedor,))
    productos = cur.fetchall()
    cur.close()

    return render_template('admin/productos_emprendedor.html', productos=productos, mensaje=mensaje)

@app.route('/admin/tienda/<int:tienda_id>/productos')
def ver_productos_tienda(tienda_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    correo_usuario = session.get('correo')
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM tienda WHERE id = %s", (tienda_id,))
    tienda = cur.fetchone()
    
    if not tienda:
        cur.close()
        flash('Tienda no encontrada.')
        return redirect(url_for('admin_inicio'))
    
    es_dueño = tienda['dueño'] == correo_usuario
    
    cur.execute("SELECT * FROM productos WHERE tienda_id = %s", (tienda_id,))
    productos = cur.fetchall()
    cur.close()
    
    return render_template('admin/productos_tienda.html', 
                           tienda=tienda, 
                           productos=productos, 
                           es_dueño=es_dueño)

# Modificación en la ruta editar_producto
@app.route('/admin/producto/<int:producto_id>/editar', methods=['GET', 'POST'])
def editar_producto(producto_id):
    if not is_logged_in() or session.get('rol') != 'emprendedor':
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    # 1. Obtener la información del producto
    cur.execute("SELECT * FROM productos WHERE id = %s AND correo_emprendedor = %s", 
                (producto_id, session['correo']))
    producto = cur.fetchone()
    
    if not producto:
        cur.close()
        flash('No tienes permiso para editar este producto.')
        return redirect(url_for('admin_inicio'))

    # 2. Obtener la información de la tienda del emprendedor
    cur.execute("SELECT * FROM tienda WHERE dueño = %s", (session['correo'],))
    tienda = cur.fetchone()

    # Si no se encuentra la tienda, redireccionar con un error
    if not tienda:
        cur.close()
        flash('Tienda no encontrada.')
        return redirect(url_for('admin_inicio'))

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        precio = request.form.get('precio')
        unidad = request.form.get('unidad')
        
        if not (nombre and descripcion and precio and unidad):
            flash('Todos los campos son obligatorios.')
        else:
            imagen1 = request.files.get('imagen1')
            imagen2 = request.files.get('imagen2')
            
            imagen1_path = producto['imagen1'] 
            imagen2_path = producto['imagen2']
            
            if imagen1:
                upload_folder = os.path.join('static', 'tiendas')
                os.makedirs(upload_folder, exist_ok=True)
                imagen1_filename = secure_filename(imagen1.filename)
                imagen1.save(os.path.join(upload_folder, imagen1_filename))
                imagen1_path = f'/static/tiendas/{imagen1_filename}'
                
            if imagen2:
                upload_folder = os.path.join('static', 'tiendas')
                os.makedirs(upload_folder, exist_ok=True)
                imagen2_filename = secure_filename(imagen2.filename)
                imagen2.save(os.path.join(upload_folder, imagen2_filename))
                imagen2_path = f'/static/tiendas/{imagen2_filename}'

            cur.execute("""
                UPDATE productos 
                SET nombre = %s, descripcion = %s, precio = %s, unidad = %s, 
                    imagen1 = %s, imagen2 = %s 
                WHERE id = %s AND correo_emprendedor = %s
            """, (nombre, descripcion, precio, unidad, 
                  imagen1_path, imagen2_path, 
                  producto_id, session['correo']))
            mysql.connection.commit()
            flash('Producto actualizado exitosamente.')
            
            # La redirección ahora es más robusta
            cur.close()
            return redirect(url_for('ver_productos_tienda', tienda_id=tienda['id']))

    cur.close()
    # Pasa ambas variables, 'producto' y 'tienda', a la plantilla
    return render_template('admin/editar_productos.html', producto=producto, tienda=tienda)
@app.route('/admin/producto/<int:producto_id>/eliminar')
def eliminar_producto(producto_id):
    if not is_logged_in() or session.get('rol') != 'emprendedor':
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM productos WHERE id = %s AND correo_emprendedor = %s", 
                (producto_id, session['correo']))
    producto = cur.fetchone()
    
    if not producto:
        cur.close()
        flash('No tienes permiso para eliminar este producto.')
        return redirect(url_for('admin_inicio'))

    cur.execute("DELETE FROM productos WHERE id = %s AND correo_emprendedor = %s", 
                (producto_id, session['correo']))
    mysql.connection.commit()
    
    cur.execute("SELECT id FROM tienda WHERE dueño = %s", (session['correo'],))
    tienda = cur.fetchone()
    cur.close()
    
    flash('Producto eliminado exitosamente.')
    if tienda:
        return redirect(url_for('ver_productos_tienda', tienda_id=tienda['id']))
    return redirect(url_for('admin_inicio'))

@app.route('/admin/editar_tienda/<int:tienda_id>', methods=['GET', 'POST'])
def editar_tienda(tienda_id):
    if not session.get('logged_in'):
        flash('Debes iniciar sesión para editar una tienda.')
        return redirect(url_for('login'))
    if session.get('rol') != 'emprendedor':
        flash('Solo los emprendedores pueden editar tiendas.')
        return redirect(url_for('admin_inicio'))
    cur = mysql.connection.cursor()
    cur.execute('SELECT * FROM tienda WHERE id = %s', (tienda_id,))
    tienda = cur.fetchone()
    if not tienda or tienda['dueño'] != session['correo']:
        flash('No tienes permiso para editar esta tienda.')
        return redirect(url_for('admin_inicio'))
    if request.method == 'POST':
        nuevo_nombre = request.form.get('nombre_tienda')
        nuevo_logo = request.form.get('logo')
        cur.execute('UPDATE tienda SET nombre_tienda = %s, logo = %s WHERE id = %s', (nuevo_nombre, nuevo_logo, tienda_id))
        mysql.connection.commit()
        flash('Tienda actualizada correctamente.')
        return redirect(url_for('admin_inicio'))
    return render_template('admin/editar_tienda.html', tienda=tienda)

@app.route('/admin/eliminar_tienda/<int:tienda_id>', methods=['GET', 'POST'])
def eliminar_tienda(tienda_id):
    if not session.get('logged_in'):
        flash('Debes iniciar sesión para eliminar una tienda.')
        return redirect(url_for('login'))
    if session.get('rol') != 'emprendedor':
        flash('Solo los emprendedores pueden eliminar tiendas.')
        return redirect(url_for('admin_inicio'))
    cur = mysql.connection.cursor()
    cur.execute('SELECT * FROM tienda WHERE id = %s', (tienda_id,))
    tienda = cur.fetchone()
    if not tienda or tienda['dueño'] != session['correo']:
        flash('No tienes permiso para eliminar esta tienda.')
        cur.close()
        return redirect(url_for('admin_inicio'))
    if request.method == 'POST':
        cur.execute('DELETE FROM tienda WHERE id = %s', (tienda_id,))
        mysql.connection.commit()
        cur.close()
        flash('Tienda eliminada correctamente.')
        return redirect(url_for('admin_inicio'))
    cur.close()
    return render_template('admin/confirmar_eliminar_tienda.html', tienda=tienda)

@app.route('/admin/carrito')
def ver_carrito():
    carrito = session.get('carrito', [])
    items = []
    subtotal_total = 0
    envio_total = 0
    total_final = 0
    
    cur = mysql.connection.cursor()
    
    # Obtener el precio de envío para todas las tiendas en el carrito (ejemplo, si es fijo por tienda)
    costos_envio = {}
    if carrito:
        tienda_ids = [item['tienda_id'] for item in carrito]
        # Esta consulta no funcionará si hay IDs duplicados.
        cur.execute("SELECT id, precio_envio FROM tienda WHERE id IN %s", (tienda_ids,))
        tiendas_con_envio = cur.fetchall()
        for tienda in tiendas_con_envio:
            costos_envio[tienda['id']] = tienda['precio_envio']
    
    for item in carrito:
        cur.execute('SELECT * FROM productos WHERE id = %s', (item['producto_id'],))
        producto = cur.fetchone()
        cur.execute('SELECT * FROM tienda WHERE id = %s', (item['tienda_id'],))
        tienda = cur.fetchone()
        
        if producto and tienda:
            # Añadir la cantidad si no existe (esto no debería ser necesario si el código anterior funciona)
            if 'cantidad' not in item:
                item['cantidad'] = 1

            subtotal_item = float(producto['precio']) * int(item['cantidad'])
            subtotal_total += subtotal_item
            
            # Asignar el costo de envío
            costo_envio_item = float(costos_envio.get(tienda['id'], 0))  # 0 por defecto si no se encuentra
            envio_total += costo_envio_item
            
            items.append({'producto': producto, 'tienda': tienda, 'cantidad': int(item['cantidad']), 'subtotal': subtotal_item})

    total_final = subtotal_total + envio_total
    cur.close()

    return render_template('admin/carrito.html', 
                           carrito=items,
                           subtotal=subtotal_total,
                           envio=envio_total,
                           total=total_final)
                           
@app.route('/admin/tienda/<int:tienda_id>/agregar_producto', methods=['GET', 'POST'])
def agregar_producto_tienda(tienda_id):
    if not is_logged_in() or session.get('rol') != 'emprendedor':
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM tienda WHERE id = %s AND dueño = %s", (tienda_id, session['correo']))
    tienda = cur.fetchone()
    if not tienda:
        cur.close()
        flash('No tienes permiso para agregar productos en esta tienda.')
        return redirect(url_for('admin_inicio'))

    mensaje = None
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        descripcion = request.form.get('descripcion')
        precio = request.form.get('precio')
        unidad = request.form.get('unidad')
        imagen1 = request.files.get('imagen1')
        imagen2 = request.files.get('imagen2')

        if not (nombre and descripcion and precio and unidad and imagen1 and imagen2):
            mensaje = 'Todos los campos son obligatorios.'
        else:
            upload_folder = os.path.join('static', 'tiendas')
            os.makedirs(upload_folder, exist_ok=True)
            imagen1_filename = secure_filename(imagen1.filename)
            imagen2_filename = secure_filename(imagen2.filename)
            imagen1.save(os.path.join(upload_folder, imagen1_filename))
            imagen2.save(os.path.join(upload_folder, imagen2_filename))

            cur.execute("""
                INSERT INTO productos (nombre, descripcion, precio, unidad, correo_emprendedor, imagen1, imagen2, tienda_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                nombre, descripcion, precio, unidad, session['correo'],
                f'/static/tiendas/{imagen1_filename}',
                f'/static/tiendas/{imagen2_filename}',
                tienda_id
            ))
            mysql.connection.commit()
            mensaje = '¡Producto agregado exitosamente!'
    cur.close()
    return render_template('admin/agregar_producto_tienda.html', tienda=tienda, mensaje=mensaje)

@app.route('/admin/agregar_al_carrito/<int:producto_id>/<int:tienda_id>', methods=['POST'])
def agregar_al_carrito(producto_id, tienda_id):
    carrito = session.get('carrito', [])
    for item in carrito:
        if item['producto_id'] == producto_id:
            item['cantidad'] += 1
            break
    else:
        carrito.append({'producto_id': producto_id, 'tienda_id': tienda_id, 'cantidad': 1})
    session['carrito'] = carrito
    flash('Producto añadido al carrito.', 'success')
    return redirect(url_for('ver_carrito'))

@app.route('/admin/actualizar_cantidad_carrito/<int:producto_id>', methods=['POST'])
def actualizar_cantidad_carrito(producto_id):
    nueva_cantidad = int(request.form.get('cantidad', 1))
    carrito = session.get('carrito', [])
    for item in carrito:
        if item['producto_id'] == producto_id:
            item['cantidad'] = max(1, nueva_cantidad)
            break
    session['carrito'] = carrito
    flash('Cantidad actualizada.', 'info')
    return redirect(url_for('ver_carrito'))

@app.route('/admin/eliminar_del_carrito/<int:producto_id>', methods=['POST'])
def eliminar_del_carrito(producto_id):
    carrito = session.get('carrito', [])
    carrito = [item for item in carrito if item['producto_id'] != producto_id]
    session['carrito'] = carrito
    flash('Producto eliminado del carrito.', 'success')
    return redirect(url_for('ver_carrito'))

# Ruta para soporte de admin
@app.route('/admin/soporte')
def admin_soporte():
    return render_template('admin/soporte.html')

@app.route('/comprar')
def comprar():
    session['carrito'] = []
    flash('¡Compra confirmada! 🎉 Tu pedido está siendo procesado. Recibirás una notificación por correo.', 'success')
    return redirect(url_for('ver_carrito'))
# ============================================================================
# RUTA DE CATEGORÍAS ADMIN
# ============================================================================

@app.route('/admin/categorias')
def admin_categorias():
    if not is_logged_in():
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, nombre, imagen FROM categoria")
    categorias = cur.fetchall()

    # Obtener tiendas con categoría
    cur.execute("""
        SELECT t.id, t.nombre_tienda, t.dueño, t.contactos, t.descripcion, t.logo, t.imagen1, t.imagen2, c.nombre AS categoria_nombre
        FROM tienda t
        LEFT JOIN categoria c ON t.categoria_id = c.id
    """)
    tiendas_global = cur.fetchall()

    favoritos = session.get('favoritos', {'tiendas': [], 'productos': []})
    for t in tiendas_global:
        t['favorito'] = t['id'] in favoritos.get('tiendas', [])

    cur.close()
    return render_template('admin/categorias.html', categorias=categorias, tiendas_global=tiendas_global)

@app.route('/admin/categoria/<int:categoria_id>/productos')
def ver_productos_categoria(categoria_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM producto WHERE categoria_id = %s", (categoria_id,))
    productos = cur.fetchall()
    cur.execute("SELECT nombre FROM categoria WHERE id = %s", (categoria_id,))
    categoria = cur.fetchone()
    return render_template('admin/productos_categoria.html', productos=productos, categoria=categoria)

# ============================================================================
# RUTAS DE FAVORITOS
# ============================================================================

@app.route('/toggle_favorito/<int:item_id>/<string:item_tipo>', methods=['POST'])
def toggle_favorito(item_id, item_tipo):
    if not is_logged_in():
        return jsonify({'success': False, 'message': 'Debes iniciar sesión para añadir favoritos.'})

    favoritos = session.get('favoritos', {'tiendas': [], 'productos': []})
    item_list = favoritos.get(f'{item_tipo}s')

    if item_id in item_list:
        item_list.remove(item_id)
        message = f'Se ha eliminado el/la {item_tipo} de tus favoritos.'
    else:
        item_list.append(item_id)
        message = f'Se ha añadido el/la {item_tipo} a tus favoritos.'

    session['favoritos'] = favoritos
    return jsonify({'success': True, 'message': message})

@app.route('/admin/favoritos')
def admin_favoritos():
    if not is_logged_in():
        return redirect(url_for('login'))
        
    favoritos = session.get('favoritos', {'tiendas': [], 'productos': []})
    favoritos_list = []
    cur = mysql.connection.cursor()
    
    # Obtener tiendas favoritas
    if favoritos.get('tiendas'):
        format_ids = ','.join(['%s'] * len(favoritos['tiendas']))
        cur.execute(f"SELECT id, nombre_tienda AS nombre, descripcion, logo AS imagen FROM tienda WHERE id IN ({format_ids})", tuple(favoritos['tiendas']))
        for t in cur.fetchall():
            t['tipo'] = 'tienda'
            favoritos_list.append(t)
    
    # Obtener productos favoritos
    if favoritos.get('productos'):
        format_ids = ','.join(['%s'] * len(favoritos['productos']))
        cur.execute(f"SELECT id, nombre, descripcion, imagen1 AS imagen FROM productos WHERE id IN ({format_ids})", tuple(favoritos['productos']))
        for p in cur.fetchall():
            p['tipo'] = 'producto'
            favoritos_list.append(p)
            
    cur.close()
    
    # Marcar como favorito para el template
    for item in favoritos_list:
        if item.get('tipo') == 'tienda':
            item['favorito'] = item['id'] in favoritos.get('tiendas', [])
        elif item.get('tipo') == 'producto':
            item['favorito'] = item['id'] in favoritos.get('productos', [])

    return render_template('admin/favoritos.html', favoritos=favoritos_list)

@app.route('/favoritos')
def ver_favoritos():
    # Esta ruta es igual a admin_favoritos pero para la zona pública, si la tuvieras
    return redirect(url_for('admin_favoritos'))


if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(debug=True)
