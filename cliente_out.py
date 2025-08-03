import socket
import time

IP_SERVIDOR = "192.168.11.200"
PORTA_COMANDO = 8000

def main():
    try:
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"Conectando a {IP_SERVIDOR}:{PORTA_COMANDO}...")
        tcp.connect((IP_SERVIDOR, PORTA_COMANDO))
        print("Conectado!")

        comandos = ["frente", "direita", "esquerda", "re", "parar"]
        idx = 0

        while True:
            cmd = comandos[idx % len(comandos)]
            print(f"Enviando comando: {cmd}")
            tcp.sendall(cmd.encode())
            idx += 1
            time.sleep(1)

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        tcp.close()
        print("Conexão fechada.")

if __name__ == "__main__":
    main()

