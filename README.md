# Carrinho Autônomo
![O carrinho](./fotos/O%20carrinho.png)

Este projeto tem como objetivo desenvolver um carrinho autônomo que pode ser controlado remotamente via joystick e também realizar navegação autônoma utilizando visão computacional e IA.

 ## 🚗 Sobre o Projeto
O Carrinho Autônomo é um projeto de robótica que utiliza Raspberry Pi,  1 PC com OpenCV e IA para controlar um carrinho inteligente. Ele pode ser operado manualmente por meio de um controle remoto ou seguir uma rota predefinida de maneira autônoma, detectando obstáculos e ajustando sua direção.

🔧 Tecnologias Utilizadas
Raspberry Pi: O "cérebro intermediario" do carrinho, responsável pelo controle de sensores, motores e câmeras, conectado ao PC central por rede Wirelles 2.4Gz A/N.

Servidor com GPU RTX2090 Super, rodando python com OpenCV: Biblioteca de visão computacional utilizada para capturar e processar imagens da câmera, via rede wirelless via UDP. e devolver comandos ao carrinho pela mesma rede via TCP 

Python: Linguagem de programação utilizada para controlar o carrinho, processar dados e integrar IA.

L298N: Driver de motor usado para controlar a direção e a velocidade dos motores.

GitHub: Para versionamento de código e colaboração no desenvolvimento.

## 🎯 Funcionalidades
Controle manual: Controle o carrinho remotamente via joystick.

Navegação autônoma: O carrinho pode navegar de forma inteligente, utilizando a câmera para detectar obstáculos e ajustar sua rota.

Visão Computacional: Processamento de imagens em tempo real para detectar obstáculos e realizar ajustes na navegação.

IA e Aprendizado: Em versões futuras, serão implementadas técnicas de aprendizado de máquina para otimizar a navegação.

⚙️ Como Rodar o Projeto
Siga os passos abaixo para configurar e rodar o Carrinho Autônomo:

### 1. Pré-requisitos
Certifique-se de ter o seguinte instalado:

Python 3 (Recomendado: Python 3.7+)

OpenCV (Biblioteca de visão computacional)

Raspberry Pi com os seguintes componentes:

Motor DC com driver L298N

Câmera Raspberry Pi ou Webcam USB

Dongle WIFI USB com antena Externa

Joystick USB (opcional, para controle manual)

### 2. Instalação das Dependências
Clone o repositório:

bash
Copiar
git clone https://github.com/seu-usuario/carrinho_autonomo.git
cd carrinho_autonomo
Instale as dependências necessárias:

bash
Copiar
pip install -r requirements.txt
### 3. Conectando o Hardware
Conecte o motor e o driver L298N à Raspberry Pi conforme o esquema de conexão.

Conecte a câmera à Raspberry Pi.

Conecte o joystick USB (se estiver usando controle manual).

### 4. Executando o Projeto
Para iniciar o controle manual via joystick:

bash
Copiar
python cliente.py
Para executar a navegação autônoma com visão computacional:

bash
Copiar
python raspi_server.py
📸 Imagens

![Visao Geral](./fotos/IMG_0146.jpg)
![Detalhes](./fotos/IMG_0147.jpg)
![Visao de cima](./fotos/IMG_0148.jpg)
![O carrinho](./fotos/O%20carrinho.png)
![O carrinho](./fotos/IMG_20250706_203533.jpg)

Adicione aqui imagens do projeto em funcionamento ou diagramas do sistema, como o layout do carrinho, a conexão dos componentes, ou o fluxo de processamento da IA.

## 🚀 Melhorias Futuras
Navegação avançada: Implementar algoritmos de mapeamento e planejamento de trajetória.

IA para decisões autônomas: Utilizar redes neurais para decisões mais dinâmicas e eficientes.

Sensores adicionais: Integrar sensores ultrassônicos e LIDAR para melhorar a navegação.

## 💡 Contribuindo
Contribuições são sempre bem-vindas! Para contribuir com o projeto:

Fork o repositório.

Crie uma branch para a sua feature (git checkout -b feature-nome-da-feature).

Faça as modificações e commit (git commit -am 'Adiciona feature X').

Envie a pull request para o repositório original.

## 👨‍💻 Desenvolvedor
Nome: Kennedy S. Amorim

GitHub: kennedy2910
