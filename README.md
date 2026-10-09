# 40K Team Pairings V13 — Android wrapper

Este proyecto prepara una **APK Android instalable** que abre la V13 alojada en Streamlit dentro de una aplicación propia. No duplica ni reimplementa el optimizador: carga la misma web que ya utilizas, por lo que mantiene las pantallas y funciones que proporcione esa versión publicada.

## Qué incluye

- Aplicación Android con nombre e icono propios.
- Pantalla inicial para introducir la URL pública de Streamlit. La URL se guarda en la tablet; no hay que escribirla cada vez.
- Botones para volver, recargar y cambiar la URL.
- JavaScript, Web Storage y cookies habilitados para que funcione Streamlit.
- Selector de archivos para las cargas de archivos de la interfaz (por ejemplo, importar el equipo JSON).
- Descargas HTTP/HTTPS enviadas al gestor de descargas de Android (por ejemplo, exportar el equipo JSON).
- Flujo de compilación en GitHub Actions que genera el APK debug, firmado automáticamente para pruebas e instalación manual.

**Requisito:** la tablet necesita conexión a Internet para abrir la app publicada y consultar estadísticas. Esta APK no contiene un servidor Streamlit local. La dirección web que se configure debe ser accesible desde la tablet.

## Cómo obtener el APK sin instalar herramientas en tu PC

1. Crea un repositorio en GitHub y sube el contenido de esta carpeta a la rama `main` (puede ser privado).
2. En GitHub, abre la pestaña **Actions** y selecciona **Build Android APK**.
3. Pulsa **Run workflow**. Espera a que termine correctamente.
4. Abre la ejecución finalizada y descarga el artefacto **40K-Team-Pairings-V13-APK**. Descomprime el ZIP del artefacto: dentro estará `app-debug.apk`.
5. Copia `app-debug.apk` a la tablet e instálalo. Android puede pedirte que permitas instalar aplicaciones desde la aplicación usada para abrir el archivo; concede ese permiso solo a la fuente en la que confíes.
6. Abre **40K Team Pairings V13**, pega la URL pública de tu Streamlit y pulsa **Guardar y abrir**.

También puedes abrir esta carpeta como proyecto en Android Studio y ejecutar la tarea Gradle `:app:assembleDebug`. El APK aparecerá en `app/build/outputs/apk/debug/app-debug.apk`.

## Importante sobre las funcionalidades

La APK es un contenedor WebView de la V13 alojada en Streamlit; no reemplaza la publicación Streamlit. Toda la lógica de pairings, estadísticas, optimización, guardado/carga y pantallas sigue siendo la que esté en la web. Se incluyen soporte para selector de archivos y descargas, pero los diálogos de carga/descarga de Streamlit dependen de su implementación web y de la versión de Android/WebView. Conviene probar en la tablet tanto importar como exportar el JSON después de instalarla.

La compilación debug sirve para instalación manual y pruebas. No es una publicación de Play Store ni una APK firmada con una clave de lanzamiento propia.

## Árbol de carpetas

- `app/`: aplicación Android WebView.
- `.github/workflows/build-apk.yml`: compilación automatizada del APK.
- `streamlit/`: copia del código V13 original y sus instrucciones para mantenerlo junto al paquete.
