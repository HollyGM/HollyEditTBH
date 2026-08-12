# HollyEditTBH

Editor independente e não oficial de saves do **TBH: Task Bar Hero** para Windows.

Projeto: <https://github.com/HollyGM/HollyEditTBH>

Versão atual: **3.3.1**

## Estado da versão

A 3.3.1 é a versão de fechamento da auditoria técnica iniciada na 3.3.0. O formato do save, a criptografia e o HMAC não foram alterados nesta revisão. O foco foi eliminar caminhos legados divergentes, endurecer o Modo Protegido, alinhar a interface do Mercado à rodada real, impedir degradação do cache público da Steam e tornar o pacote reproduzível e verificável no CI.

## Recursos principais

- abre e salva `SaveFile_Live.es3` com criptografia e assinatura de integridade;
- cria backup com data e hora antes de substituir o arquivo original;
- grava por arquivo temporário + substituição atômica;
- abre, edita e exporta dumps JSON pela interface validada;
- interface em português do Brasil, com contraste, raridade visual e fluxo guiado;
- retratos próprios para as seis classes de herói;
- busca sem diferença entre acentos/maiúsculas e filtros por raridade e tipo;
- filtros no inventário, armazém, troca, criação e edição de itens;
- encantamentos limitados a equipamentos, espaços e atributos compatíveis;
- **Central de Inteligência** com análise e prévia antes das alterações automáticas;
- pontuação contínua de equipamentos por raridade, nível conhecido, afinidade do herói, tiers e ocupação dos encantamentos;
- perfis de heróis em `hero_profiles.json`, explicitamente heurísticos e calibráveis;
- otimização global exata: um item não é reutilizado e nenhum herói é rebaixado para beneficiar outro;
- compatibilidade correta para amuleto, brinco, anel e abraçadeira;
- fila conservadora de candidatos ao Mercado usando somente itens já existentes e não modificados;
- snapshot público e cacheado do Steam Community Market usado apenas como referência de preço;
- proteção contra substituir um snapshot bom por resposta parcial/truncada da Steam;
- preparação do Mercado limitada por padrão aos **4 slots da rodada**;
- fila de reciclagem que preserva a melhor cópia e não converte itens automaticamente;
- desbloqueio conservador de tutoriais, heróis, pets, atributos e receitas conhecidas;
- atualização automática do catálogo com validação contra respostas parciais e regressões abruptas;
- Modo Protegido com detecção do jogo aberto, mudança externa do save e isolamento de operações de maior risco;
- validação de referências, identificadores, locais e estruturas de encantamento;
- executável Windows validado por testes, PyInstaller, metadados e smoke test no GitHub Actions.

## Modo Protegido

O Modo Protegido fica ativo por padrão e, na 3.3.1, passou a ter uma fronteira mais clara:

- não cria itens inexistentes no save carregado;
- não duplica itens;
- não equipa itens criados durante a sessão;
- itens modificados/criados continuam excluídos da inteligência de Mercado;
- bloqueia salvamento enquanto o Taskbar Hero estiver aberto;
- bloqueia salvamento quando o arquivo mudou no disco depois de ser carregado;
- mantém backup e validação estrutural antes da gravação.

A criação e duplicação local continuam disponíveis somente após desativação consciente do Modo Protegido. Isso não transforma a operação em segura ou aceita pelo jogo.

## Aviso sobre sanções e Mercado Steam

O desenvolvedor do TBH informou oficialmente que usuários que criaram ou obtiveram itens por métodos anormais podem receber restrição de acesso ao jogo ou ao Mercado. Por esse motivo, a 3.3.1 não apresenta criação de item como operação segura e o Modo Protegido a bloqueia por padrão.

Fonte oficial: <https://steamcommunity.com/app/3678970/allnews/>

A política-base de Mercado confirmada em **6 de julho de 2026** mantém a negociação de equipamentos de alto grau condicionada a nova liberação oficial. No aviso de reabertura do Mercado, foram informados 4 slots de listagem, cooldown de 8 horas por slot e restrição temporária para Cósmico, Divino e Celestial, com exceção indicada para Soulstones.

O HollyEditTBH:

- não acessa login, cookies privados ou inventário autenticado da Steam;
- não envia itens à Steam;
- não promete elegibilidade, preço, venda ou liquidez;
- não trata quantidade de anúncios concorrentes como prova de demanda;
- usa páginas públicas somente como sinal auxiliar e cacheado;
- preserva um cache anterior quando a nova coleta parece truncada;
- mantém a decisão final de listagem dentro do jogo/Steam.

Para contas que efetivamente disponham de mais slots, o limite técnico pode ser ajustado pela variável de ambiente `HOLLYEDIT_MARKET_SLOTS`, entre 1 e 12.

## Uso recomendado

1. Feche o Taskbar Hero.
2. Abra `SaveFile_Live.es3` pelo HollyEditTBH.
3. Mantenha o **Modo Protegido** ativo para reorganização, autoequipe, análise e manutenção do save.
4. Use **Validar save** antes de gravar.
5. Confira a prévia de qualquer operação automática.
6. Clique em **Salvar alterações** somente após a conferência. Um backup será criado antes da substituição.

## Central de Inteligência

### Equipamentos

A análise individual compara o item equipado com opções existentes. A otimização global distribui os itens entre os heróis simultaneamente, sem reutilização e sem piorar a nota atual de um herói apenas para elevar a soma dos demais.

Os perfis padrão são heurísticos e não são apresentados como tier list oficial. Builds específicas para farm, chefe ou composição podem exigir pesos diferentes.

### Mercado

A fila trabalha com itens originais do save, não bloqueados, não equipados e não alterados na sessão. O preço público observado é somente referência de ordenação. Encantamentos não aumentam artificialmente a prioridade de venda.

### Reciclagem

A análise identifica duplicados de menor prioridade, preserva a melhor cópia e apenas organiza a fila. Síntese/reciclagem continua sendo feita dentro do jogo.

### Desbloqueios

Tutoriais, heróis, pets, grupos de atributos e receitas conhecidas podem ser liberados localmente. Versões desconhecidas do save não recebem chaves futuras inventadas.

## Recursos que não são forçados

- **Conquistas Steam:** não são tratadas como campos locais do `.es3` e nenhuma API externa é usada para forçá-las.
- **Cosméticos sem estrutura local conhecida:** não são fabricados pelo editor.
- **Elegibilidade Steam:** não é criada ou alterada pelo HollyEditTBH.
- **Itens para venda por dinheiro real:** itens criados/modificados pelo editor ficam fora da inteligência de Mercado.

## Entrada oficial do código-fonte

A entrada suportada da versão final é:

```powershell
py -3.12 hollyedittbh_final.py
```

`hollyedittbh_next.py` contém a camada de inteligência 3.3.x. O núcleo histórico foi isolado em `legacy_editor.py` e é reutilizado internamente. `tbh_save_editor.py` funciona apenas como ponte de compatibilidade: quando importado, resolve para o núcleo legado; quando executado diretamente, redireciona para a entrada final. Assim, a execução direta não inicia mais uma versão antiga da aplicação.

## Testes

Executar a mesma suíte usada pelo CI:

```powershell
py -3.12 -m unittest -v test_hollyedittbh.py test_intelligence_v33.py test_market_ranking_v33.py test_hero_profiles_v33.py test_final_audit_v331.py
```

O CI também executa:

- `python -m compileall -q .`;
- build pelo PyInstaller;
- conferência de `FileVersion 3.3.1`;
- inicialização real do `.exe` por 5 segundos;
- geração de `SHA256SUMS.txt`;
- publicação de `HollyEditTBH.exe` e checksum no mesmo artefato.

## Gerar o executável

```powershell
py -3.12 -m pip install pyinstaller
py -3.12 -m PyInstaller --noconfirm --clean HollyEditTBH.spec
```

Saída esperada:

```text
dist/HollyEditTBH.exe
```

## Atalhos

- `Ctrl+O`: abrir save;
- `Ctrl+S`: salvar alterações;
- `Ctrl+Shift+E`: exportar JSON.

## Limites

Nenhum editor de save pode oferecer garantia contra sanções, incompatibilidade futura ou mudança de regras do servidor. O Modo Protegido reduz alterações acidentais e separa operações de maior risco; não oculta modificações nem contorna sistemas de detecção.
