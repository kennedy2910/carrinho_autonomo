import socket
import keyboard
import time

HOST = '192.168.11.200'  # IP do Raspberry Pi
PORT = 8000

# === Estado ===
potencia = 0
ultima_potencia_enviada = -1
modo = None  # 'W' ou 'S'
direcao_anterior = None

# === Conexão ===
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((HOST, PORT))
print("Conectado ao carrinho! Use W/S para acelerar/re, A/D para direção.")

try:
    while True:
        # ===== DIREÇÃO =====
        if keyboard.is_pressed('a'):
            if direcao_anterior != 'A':
                sock.sendall(b'A')
                direcao_anterior = 'A'
                print(">> Virando esquerda")
        elif keyboard.is_pressed('d'):
            if direcao_anterior != 'D':
                sock.sendall(b'D')
                direcao_anterior = 'D'
                print(">> Virando direita")
        else:
            if direcao_anterior is not None:
                sock.sendall(b'N')  # comando neutro ao soltar tecla
                print(">> Direção parada")
                direcao_anterior = None

        # ===== ACELERAÇÃO =====
        if keyboard.is_pressed('w'):
            if modo != 'W':
                sock.sendall(b'W')
                print(">> Modo frente")
                modo = 'W'
                potencia = 10
            elif potencia < 100:
                potencia += 10
                if potencia > 100:
                    potencia = 100

            if potencia != ultima_potencia_enviada:
                sock.sendall(str(potencia // 10).encode())
                ultima_potencia_enviada = potencia
                print(f">> Potência: {potencia}%")

            time.sleep(0.1)

        elif keyboard.is_pressed('s'):
            if modo != 'S':
                sock.sendall(b'S')
                print(">> Modo ré")
                modo = 'S'
                potencia = 10
            elif potencia < 100:
                potencia += 10
                if potencia > 100:
                    potencia = 100

            if potencia != ultima_potencia_enviada:
                sock.sendall(str(potencia // 10).encode())
                ultima_potencia_enviada = potencia
                print(f">> Potência ré: {potencia}%")

            time.sleep(0.1)

        else:
            if modo:
                sock.sendall(b'P')
                print(">> Parando motor")
                potencia = 0
                ultima_potencia_enviada = -1
                modo = None
            time.sleep(0.05)

except KeyboardInterrupt:
    sock.sendall(b'P')
    sock.sendall(b'N')
    sock.close()
    print("\nConexão encerrada.")
