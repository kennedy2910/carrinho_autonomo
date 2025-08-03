import pygame
import time

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("Nenhum joystick encontrado.")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()

print(f"Joystick detectado: {joystick.get_name()}")
print("Pressione botões ou mova eixos para ver os valores. Ctrl+C para sair.")

clock = pygame.time.Clock()

try:
    while True:
        pygame.event.pump()

        # Botões
        for i in range(joystick.get_numbuttons()):
            if joystick.get_button(i):
                print(f"[{time.time()}] Botão {i} pressionado")

        # Eixos analógicos (gatilhos e sticks)
        for i in range(joystick.get_numaxes()):
            valor = joystick.get_axis(i)
            if abs(valor) > 0.05:
                print(f"[{time.time()}] Eixo {i} valor: {valor:.2f}")

        # HAT (D-pad)
        for i in range(joystick.get_numhats()):
            hat = joystick.get_hat(i)
            if hat != (0, 0):
                print(f"[{time.time()}] HAT {i} direção: {hat}")

        clock.tick(30)

except KeyboardInterrupt:
    print("Encerrado pelo usuário.")
finally:
    pygame.quit()