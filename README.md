# HollyEditTBH

Editor de saves do Taskbar Hero para Windows.

Projeto independente e não oficial: <https://github.com/HollyGM/HollyEditTBH>

Versão atual: **3.3.0**

## Recursos

- abre e salva `SaveFile_Live.es3` com criptografia e assinatura de integridade;
- cria backup com data e hora antes de substituir o arquivo original;
- abre, edita e exporta dumps JSON;
- interface em português do Brasil com paleta centralizada, maior contraste e indicação visual por raridade;
- retratos próprios para as seis classes de herói;
- busca sem diferença entre acentos/maiúsculas e filtros por raridade e tipo;
- filtros no inventário, armazém, criação, troca e edição de itens;
- encantamentos limitados a equipamentos, espaços e atributos compatíveis;
- **Central de Inteligência** que analisa antes de alterar e mostra uma prévia das ações;
- pontuação contínua e explicável de equipamento, combinando raridade, nível quando conhecido, afinidade do herói, tiers e ocupação dos encantamentos;
- perfis de atributos dos heróis externalizados em `hero_profiles.json`, calibráveis e identificados como heurísticos, não como tier list oficial;
- otimização individual e otimização global exata, sem reutilizar o mesmo item, sem favorecer a ordem de `heroSaveDatas` e sem rebaixar um herói para beneficiar outro;
- compatibilidade corrigida para amuleto, brinco, anel e abraçadeira;
- análise conservadora de candidatos ao Mercado com snapshot público e cacheado do Steam Community Market;
- preparação do Mercado limitada por padrão a uma rodada de quatro slots e sem tratar preço ou elegibilidade como garantia;
- itens criados ou alterados pelo editor continuam excluídos dos candidatos ao Mercado;
- fila conservadora de reciclagem que preserva a melhor cópia e nunca apaga itens;
- desbloqueio conservador de tutoriais, heróis, pets, atributos e receitas conhecidas;
- compatibilidade conservadora com versões novas do save: receitas novas nunca são inventadas;
- atualização automática do catálogo com validação de integridade, proteção contra resposta parcial e regressão abrupta do número de itens;
- Modo Protegido que detecta o jogo aberto, mudanças externas do arquivo e limita lotes;
- valida referências de itens, espaços, encantamentos e identificadores;
- repara inconsistências seguras antes de salvar;
- gerencia inventário, sete abas do armazém, heróis, equipamentos e coleções;
- inclui base de itens, ícones, retratos e perfis de heróis no executável.

## Uso seguro

1. Feche o Taskbar Hero antes de editar o save.
2. Clique em **Abrir save**. O programa abre diretamente a pasta padrão do jogo quando ela existe.
3. Faça as alterações e use **Validar save**.
4. Confira a prévia da Central de Inteligência antes de aplicar ações automáticas.
5. Clique em **Salvar alterações**. Um backup com data e hora será criado na mesma pasta do save.

## O que faz a Central de Inteligência

- **Melhorar um herói:** compara o item equipado com as opções existentes e explica a nota usada para a indicação.
- **Otimizar todos os heróis:** resolve a distribuição dos itens globalmente. Um mesmo item não pode ser entregue a dois heróis e nenhum herói pode ficar abaixo da própria nota atual para favorecer outro.
- **Preparar itens para o Mercado:** seleciona apenas itens existentes e não modificados, respeita as restrições locais conhecidas e usa cotações públicas da Steam somente como sinal de ordenação. Não envia itens à Steam.
- **Separar duplicados para reciclagem:** preserva a melhor cópia e organiza as demais. Não apaga nem converte itens.
- **Liberar recursos locais:** prepara desbloqueios conhecidos de tutoriais, heróis, pets, atributos e receitas. Não inventa fases e não altera progresso de servidor.

Em todos os casos, a mudança só chega ao arquivo depois de clicar em **Salvar alterações**.

## Mercado Steam e proteção

- A aceitação final, cooldown, quantidade efetiva de slots e preço são definidos pelo jogo e pela Steam.
- A preparação padrão usa quatro slots por rodada. Para instalações em que a conta realmente disponha de mais slots, o limite técnico pode ser ajustado pela variável de ambiente `HOLLYEDIT_MARKET_SLOTS`, entre 1 e 12.
- Itens criados ou alterados na sessão nunca entram automaticamente nas filas de Mercado ou reciclagem.
- A política conservadora embutida bloqueia equipamento Comum, Incomum e Raro e mantém Cósmico, Divino e Celestial fora de novas recomendações enquanto não houver confirmação oficial posterior de liberação; materiais e exceções conhecidas, como Soulstones, são tratados separadamente.
- Encantamentos não aumentam a prioridade de venda no editor; a listagem é tratada separadamente da qualidade de combate.
- A consulta ao Steam Community Market usa apenas páginas públicas, sem login, cookies privados ou tentativa de contornar limitação de requisições. O snapshot é cacheado por horas e pode ficar parcial ou desatualizado se a Steam limitar a resposta.
- Não existe garantia “anti-banimento”. O Modo Protegido reduz conflitos e erros; ele não oculta alterações nem burla detecção.
- Feche o jogo normalmente antes de salvar. Se o arquivo mudar no disco após ser carregado, reabra o save.

## Desbloqueios que não são forçados pelo editor

- **Conquistas Steam:** não são tratadas como campos locais do `.es3` e o editor não chama APIs da Steam para forçá-las. Alterações legítimas de progressão local podem ser reavaliadas pelo próprio jogo, mas isso não é apresentado como garantia de conquista.
- **Cosméticos:** nenhum campo local confiável de coleção cosmética foi identificado no formato de save coberto por esta versão. O programa não fabrica estruturas desconhecidas nem tenta contornar validação do servidor.

## Atalhos

- `Ctrl+O`: abrir save;
- `Ctrl+S`: salvar alterações;
- `Ctrl+Shift+E`: exportar JSON.

## Desenvolvimento

A entrada da versão 3.3.0 é `hollyedittbh_next.py`. O arquivo `tbh_save_editor.py` permanece como camada legada preservada e reutilizada pela nova interface.

Executar pelo código-fonte:

```powershell
py -3.12 hollyedittbh_next.py
```

Executar a suíte completa usada pelo CI:

```powershell
py -3.12 -m unittest -v test_hollyedittbh.py test_intelligence_v33.py
```

Gerar o executável:

```powershell
py -3.12 -m pip install pyinstaller
py -3.12 -m PyInstaller --noconfirm --clean HollyEditTBH.spec
```

O workflow de CI em Windows também valida compilação do código, testes, metadados `3.3.0`, inicialização do executável e publicação do artefato de teste.
