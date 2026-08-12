# HollyEditTBH

Editor de saves do Taskbar Hero para Windows.

Projeto independente e não oficial: <https://github.com/HollyGM/HollyEditTBH>

Versão atual: **3.1.0**

## Recursos

- abre e salva `SaveFile_Live.es3` com criptografia e assinatura de integridade;
- cria um backup com data e hora antes de substituir o arquivo original;
- abre, edita e exporta dumps JSON;
- interface em português do Brasil, com fluxo visual mais simples;
- retratos próprios para as seis classes de herói;
- busca sem diferença entre acentos/maiúsculas e filtros por raridade e tipo;
- filtros no inventário, armazém, criação, troca e edição de itens;
- encantamentos limitados a equipamentos, espaços e atributos compatíveis;
- Assistente Guiado que explica cada tarefa, mostra a análise antes de alterar e separa claramente o que o programa faz e não faz;
- otimização automática de um herói ou de todos, sem reutilizar o mesmo item;
- organização de pré-candidatos ao Mercado em uma aba escolhida do armazém;
- fila conservadora de reciclagem que preserva a melhor cópia e nunca apaga itens;
- desbloqueio conservador de tutoriais, heróis, pets, atributos e receitas conhecidas;
- Modo Protegido que detecta o jogo aberto, mudanças externas do arquivo e limita lotes;
- valida referências de itens, espaços, encantamentos e identificadores;
- repara inconsistências seguras antes de salvar;
- gerencia inventário, sete abas do armazém, heróis, equipamentos e coleções;
- inclui a base de itens, ícones e retratos no executável.

## Uso seguro

1. Feche o Taskbar Hero antes de editar o save.
2. Clique em **Abrir save**. O programa abre diretamente a pasta padrão do jogo.
3. Faça as alterações e use **Validar save**.
4. Clique em **Salvar alterações**. Um backup com data e hora será criado na mesma pasta do save.

## O que faz o Assistente Guiado

- **Melhorar os heróis:** compara os equipamentos já existentes e mostra uma prévia das trocas. Não cria itens.
- **Preparar itens para o Mercado:** seleciona candidatos locais conservadores e, após confirmação, organiza-os em uma aba do armazém. Não envia itens à Steam.
- **Separar duplicados para reciclagem:** preserva a melhor cópia e organiza as demais. Não apaga nem converte itens.
- **Liberar recursos locais:** prepara desbloqueios conhecidos de tutoriais, heróis, pets, atributos e receitas. Não inventa fases e não altera servidor.

Em todos os casos, a mudança só chega ao arquivo depois de clicar em **Salvar alterações**.

## Mercado Steam e proteção

- A análise de Mercado apenas organiza o save local. A aceitação, o prazo e o preço são definidos pelo jogo e pela Steam.
- Itens criados ou alterados na sessão nunca entram automaticamente nas filas de Mercado ou reciclagem.
- O último aviso oficial verificado em 12/08/2026 ainda restringia Cósmico, Divino e Celestial, com exceção indicada para Soulstones.
- Encantamentos e decorações são removidos pelo próprio jogo quando um item é listado.
- Não existe garantia “anti-banimento”. O Modo Protegido reduz conflitos e erros; ele não oculta alterações nem burla detecção.
- Feche o jogo normalmente antes de salvar. Se o arquivo mudar no disco após ser carregado, reabra o save.

Atalhos: `Ctrl+O` abre um arquivo, `Ctrl+S` salva e `Ctrl+Shift+E` exporta JSON.

## Desenvolvimento

Execute os testes com:

```powershell
py -3.14 -m unittest -v
```

Gere o executavel com:

```powershell
py -3.14 -m PyInstaller --noconfirm --clean HollyEditTBH.spec
```
