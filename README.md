# HollyEditTBH

Editor independente e não oficial de saves do **TBH: Task Bar Hero** para Windows.

Projeto: <https://github.com/HollyGM/HollyEditTBH>

Versão proposta: **3.3.2**

## Estado da versão

A 3.3.2 é um patch de confiabilidade sobre a 3.3.1 auditada. O formato do save, AES, derivação de chave, HMAC de `SystemInfo`, inteligência de equipamentos e política de Mercado não foram alterados. O foco desta revisão é fechar uma janela de concorrência na persistência, tornar o Modo Protegido fail-safe quando verificações locais falham e fixar a toolchain de build usada pelo CI.

A auditoria histórica da 3.3.1 permanece em `AUDITORIA_FINAL_v3.3.1.md` e continua sendo a referência das garantias já conquistadas.

## Recursos principais

- abre e salva `SaveFile_Live.es3` com criptografia e assinatura de integridade;
- cria backup antes de substituir um save previamente carregado;
- prepara o novo save em arquivo temporário no mesmo diretório, executa `flush` + `fsync` e valida SHA-256 antes do commit;
- no Windows, usa `ReplaceFileW` para combinar em uma única chamada nativa a substituição e a captura do conteúdo anterior;
- trata os estados de falha documentados de `ReplaceFileW` e tenta restaurar o caminho principal sem sobrescrever um arquivo concorrente que tenha reaparecido;
- durante rollback, só descarta o arquivo substituído se o SHA-256 provar que ele é o blob gerado pelo editor; uma segunda versão concorrente é preservada para recuperação;
- rejeita e restaura uma versão externa quando o conteúdo substituído não corresponde ao SHA-256 da origem carregada;
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
- proteção contra substituir um snapshot completo por resposta parcial/truncada da Steam;
- preparação do Mercado limitada por padrão aos **4 slots da rodada**;
- fila de reciclagem que preserva a melhor cópia e não converte itens automaticamente;
- desbloqueio conservador de tutoriais, heróis, pets, atributos e receitas conhecidas;
- atualização automática do catálogo com validação contra respostas parciais e regressões abruptas;
- Modo Protegido com detecção do jogo aberto, mudança externa do save e isolamento de operações de maior risco;
- assinatura local por tamanho, timestamp e SHA-256 do conteúdo para detectar alteração externa mesmo com tamanho e horário preservados;
- estado de `integrity_valid` preservado corretamente em falhas de persistência;
- executável Windows validado por testes, PyInstaller, metadados, smoke test e checksum no GitHub Actions.

## Persistência 3.3.2

A 3.3.1 já gravava por temporário + `fsync` + `os.replace`, mas a verificação de alteração externa era feita na camada de interface antes da persistência. Isso deixava uma janela curta entre a conferência e a substituição efetiva.

Na 3.3.2, `VerifiedSaveFile` registra o SHA-256 dos bytes exatos carregados. Antes da gravação, o novo blob é gerado em temporário e validado. No Windows, `ReplaceFileW` combina em uma única função as etapas de substituição e pode gerar simultaneamente uma cópia do arquivo substituído. O hash dessa cópia é então comparado com a origem esperada:

- se coincidir, o commit é aceito e o fingerprint interno é atualizado;
- se divergir, a versão externa capturada é restaurada e o novo blob é rejeitado;
- se a troca falhar antes de alterar o caminho, o original permanece no lugar;
- se `ReplaceFileW` retornar um estado documentado em que o original já foi movido para o backup e o caminho principal ficou ausente, a camada tenta restaurar o original sem substituir qualquer arquivo que tenha reaparecido;
- se outra gravação externa ocorrer durante a tentativa de rollback, essa segunda versão é capturada, validada como conteúdo não pertencente ao editor e preservada em arquivo de recuperação em vez de ser apagada;
- se ocorrer uma condição excepcional após a troca e a restauração automática não puder ser confirmada, a cópia capturada é preservada e não é apagada silenciosamente.

O produto suportado é Windows. Fora do Windows existe apenas um fallback para desenvolvimento; os gates de release e as garantias de recuperação são validados no runner Windows.

## Modo Protegido

O Modo Protegido permanece ativo por padrão e mantém todas as barreiras da 3.3.1:

- não cria itens inexistentes no save carregado;
- não duplica itens;
- não equipa itens criados durante a sessão;
- itens modificados/criados continuam excluídos da inteligência de Mercado;
- bloqueia salvamento enquanto o Taskbar Hero estiver aberto;
- bloqueia salvamento quando o conteúdo do arquivo mudou no disco depois de ser carregado;
- na 3.3.2, também bloqueia se a assinatura inicial do save não puder ser obtida;
- na 3.3.2, falha/timeout/retorno inválido do `tasklist` é tratado conservadoramente como estado inseguro, em vez de presumir que o jogo está fechado.

A criação e duplicação local continuam disponíveis somente após desativação consciente do Modo Protegido. Isso não transforma a operação em segura ou aceita pelo jogo.

## Mercado Steam

A política conservadora da 3.3.1 foi preservada:

- 4 slots por rodada por padrão;
- itens criados ou modificados pelo editor ficam fora da inteligência de Mercado;
- encantamentos não aumentam artificialmente a prioridade de venda;
- quantidade de anúncios concorrentes não é tratada como prova de liquidez;
- snapshot completo anterior prevalece sobre nova coleta parcial;
- o editor não acessa login, cookies privados ou inventário autenticado da Steam;
- não envia itens à Steam e não promete elegibilidade, preço, venda ou demanda.

O User-Agent da coleta pública passou a usar `APP_VERSION`, evitando divergência futura entre a versão do aplicativo e o identificador da consulta, sem mudar a política de rede.

Para contas que efetivamente disponham de mais slots, o limite técnico pode ser ajustado pela variável de ambiente `HOLLYEDIT_MARKET_SLOTS`, entre 1 e 12.

## Entrada oficial do código-fonte

A entrada suportada continua sendo:

```powershell
py -3.12 hollyedittbh_final.py
```

`legacy_editor.py` contém o núcleo histórico isolado. `tbh_save_editor.py` permanece apenas como ponte de compatibilidade: importações resolvem para o núcleo legado e execução direta redireciona para `hollyedittbh_final.py`. O `HollyEditTBH.spec` continua empacotando a entrada final; não existem duas aplicações independentes.

## Testes

Executar a mesma suíte usada pelo CI:

```powershell
py -3.12 -m unittest -v test_hollyedittbh.py test_intelligence_v33.py test_market_ranking_v33.py test_hero_profiles_v33.py test_final_audit_v331.py test_hardening_v332.py
```

A suíte proposta contém **68 testes automatizados**: os 55 do baseline 3.3.1 mais 13 regressões de endurecimento da 3.3.2. Entre as novas regressões estão conflito externo, corrida no instante do commit, falha da substituição, recuperação do estado parcial documentado de `ReplaceFileW`, concorrência durante rollback sem perda da versão mais nova, preservação de backups, saves sucessivos, caminho Unicode, assinatura indisponível e falhas de detecção do processo do jogo.

O CI também executa:

- `python -m compileall -q .`;
- smoke test de 3 segundos da ponte `tbh_save_editor.py`;
- instalação da toolchain fixada em `requirements-build.txt`;
- build pelo PyInstaller;
- conferência de `FileVersion 3.3.2`;
- inicialização real do `.exe` por 5 segundos;
- geração de `SHA256SUMS.txt`;
- validação de que `dist` contém somente `HollyEditTBH.exe` e `SHA256SUMS.txt`;
- publicação dos dois arquivos no mesmo artefato.

As Actions externas continuam fixadas aos SHAs auditados de `actions/checkout v7.0.1`, `actions/setup-python v7.0.0` e `actions/upload-artifact v7.0.1`, com `permissions: contents: read`. O Python do CI é **3.12.10** e as dependências de empacotamento usadas pelo build estão explicitamente fixadas em `requirements-build.txt`.

## Gerar o executável

```powershell
py -3.12 -m pip install -r requirements-build.txt
py -3.12 -m PyInstaller --noconfirm --clean HollyEditTBH.spec
```

Saída esperada:

```text
dist/HollyEditTBH.exe
```

## Verificação do pacote

O GitHub Actions publica `HollyEditTBH.exe` e `SHA256SUMS.txt` no mesmo artefato. O checksum deve ser conferido a partir do arquivo pertencente ao **mesmo build**, pois o empacotamento PyInstaller não é tratado como byte a byte reprodutível entre execuções independentes.

## Distribuição e decisões do mantenedor

Três itens permanecem deliberadamente fora de automação nesta revisão:

- **Assinatura digital do executável:** tecnicamente recomendável, mas depende de certificado/chave privada e de política de custódia de segredo. Nenhum certificado foi inventado ou incluído no repositório.
- **GitHub Release/tag:** pode ser automatizado no futuro após merge por workflow separado e permissões mínimas, mas a 3.3.2 não publica release automaticamente. O repositório continua sem release/tag criado por esta mudança.
- **Licença:** o repositório não recebe uma licença por decisão automática. A escolha da licença é decisão jurídica/do proprietário e deve ser feita expressamente pelo mantenedor.

## Atalhos

- `Ctrl+O`: abrir save;
- `Ctrl+S`: salvar alterações;
- `Ctrl+Shift+E`: exportar JSON.

## Limites

Nenhum editor de save pode oferecer garantia contra sanções, incompatibilidade futura ou mudança de regras do servidor. O Modo Protegido reduz alterações acidentais e separa operações de maior risco; não oculta modificações nem contorna sistemas de detecção.
