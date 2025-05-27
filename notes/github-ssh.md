## Cómo conectar Linux a GitHub para hacer push (SSH)

Sigue estos pasos para configurar tu sistema Linux y poder hacer push a GitHub usando SSH:

**1. Comprueba si ya tienes claves SSH**
```bash
ls -al ~/.ssh
```
Busca archivos como `id_rsa` y `id_rsa.pub` o `id_ed25519` y `id_ed25519.pub`. Si ya existen, puedes usarlas; si no, genera una nueva clave[3][1].

**2. Genera una nueva clave SSH (si es necesario)**
```bash
ssh-keygen -t ed25519 -C "tu_email@example.com"
```
Presiona Enter para aceptar la ubicación por defecto y, si quieres, pon una passphrase[3][4].

**3. Inicia el agente SSH y añade tu clave**
```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```
(Si usaste `id_rsa`, cambia el nombre del archivo)[1][3].

**4. Añade la clave pública a tu cuenta de GitHub**
- Muestra tu clave pública:
  ```bash
  cat ~/.ssh/id_ed25519.pub
  ```
- Copia el contenido.
- Ve a GitHub → Settings (Configuración) → SSH and GPG keys → New SSH key.
- Pon un título y pega la clave. Guarda los cambios[2][3][4][5].

**5. Prueba la conexión**
```bash
ssh -T git@github.com
```
Si todo está correcto, verás un mensaje de bienvenida de GitHub[3].

**6. Usa la URL SSH al clonar o añadir el remoto**
Ejemplo:
```bash
git clone git@github.com:usuario/repositorio.git
```
o si ya tienes el repo:
```bash
git remote set-url origin git@github.com:usuario/repositorio.git
```

Ahora puedes hacer push, pull y fetch sin introducir usuario/contraseña cada vez[3][6].

---

**Resumen de comandos clave:**
```bash
ssh-keygen -t ed25519 -C "tu_email@example.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
ssh -T git@github.com
```

Con esto, tu Linux estará conectado a GitHub para push por SSH.

Citations:
[1] https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent
[2] https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account
[3] https://dev.to/aditya8raj/setup-github-ssh-keys-for-linux-1hib
[4] https://www.theserverside.com/blog/Coffee-Talk-Java-News-Stories-and-Opinions/GitHub-SSH-Key-Setup-Config-Ubuntu-Linux
[5] https://www.inmotionhosting.com/support/server/ssh/how-to-add-ssh-keys-to-your-github-account/
[6] https://docs.github.com/en/authentication/connecting-to-github-with-ssh
[7] https://www.youtube.com/watch?v=s6KTbytdNgs
[8] https://www.atlassian.com/git/tutorials/git-ssh

---
Respuesta de Perplexity: https://www.perplexity.ai/search/en-cadiz-que-impuestos-se-paga-rSjgcr7oRamYxvoiVMW5Rw?utm_source=copy_output
