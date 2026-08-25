# HollyEditTBH

Editor independente e não oficial de saves do **TBH: Task Bar Hero**, para **Windows, Linux e macOS**.

Projeto: <https://github.com/HollyGM/HollyEditTBH>

Versão proposta: **3.4.0**

## Revisão de usabilidade, português e portabilidade

Esta revisão auditou a interface inteira e corrigiu o que estava quebrado ou inacessível. Nenhuma alteração toca o formato do save, AES, derivação de chave, HMAC de `SystemInfo` ou a persistência transacional.

**Funções que não funcionavam**

- **a otimização global de heróis era código morto.** `open_auto_equip_all_preview` — o único caminho que usa a alocação exata de `intelligence_engine.optimal_unique_assignment` — não tinha nenhum chamador em lugar nenhum do programa. O recurso estava implementado e testado, mas era inacessível pela interface. Agora tem entrada no painel de heróis (**Otimizar todos os heróis**) e na aba **Equipamentos** da Central de Inteligência;
- **a prévia dessa otimização descrevia o algoritmo errado.** O texto dizia "a ordem dos heróis decide quem fica com um item disputado — não é um ótimo global", que descreve a versão gulosa do núcleo legado. O produto sempre roda a camada intermediária, que resolve o ótimo exato. Cada camada agora declara o próprio critério (`auto_equip_all_strategy_note`);
- **`legacy_editor.py` abria o editor ao ser executado direto.** O README afirmava que ele recusava, como `hollyedittbh_next.py`; na prática entregava um editor sem persistência transacional, sem detecção fail-safe do jogo aberto e sem os bloqueios do Modo Protegido. Agora recusa de fato;
- **nenhuma tabela tinha barra de rolagem.** As 462 posições do armazém e os milhares de registros da aba "Todos os itens" só podiam ser percorridos pela roda do mouse, sem indicação de quanto havia abaixo;
- **"Definir em todos" aplicava sem confirmação e mentia na contagem.** Era a única operação em massa sem confirmação, e o resumo dizia "atualizado em N registros" contando também os registros que não possuem o campo. Agora conta apenas os alcançados, confirma antes e avisa quando nenhum registro tem o campo;
- **"Desbloquear pets" marcava o save como alterado mesmo sem alterar nada.** Agora confirma, age só sobre os pets bloqueados e informa quando já estão todos liberados;
- **falhas de rede apareciam como exceção crua.** A barra de status exibia `<urlopen error Tunnel connection failed: 403 Forbidden>`, que parece defeito do programa em vez de ausência de internet.

**O que o usuário vê**

- o cabeçalho de detalhe mostrava o que estava sendo editado, mas nunca **de onde**. Agora exibe o local do item (`Onde está: Inventário - espaço 1 · ID único 1001`) e avisa em destaque quando o item não tem local no save;
- o painel de equipamentos mostra dez cartões sem dizer de quem são. Agora traz **nome e nível do herói ativo** acima da grade;
- a prévia da otimização global passou a mostrar a origem de cada item recomendado;
- diálogos que ignoravam a adaptação de tela (`configure_dialog`) foram padronizados, e todos passaram a ser modais com fechamento por `Esc`.

**Português**

Cerca de 40 mensagens visíveis estavam sem acento — "copia", "sao", "automatico", "excluido", "Alocacao automatica concluida", "Reparacao concluida", "Informacoes", "colecao" — e duas listas de locais rotulavam um herói desconhecido como `Hero 101` em vez de `Herói 101`. Um teste automatizado (`test_no_visible_message_lost_its_accents`) percorre todos os literais de interface e falha se um novo texto perder o acento.

**Portabilidade**

Três pontos assumiam Windows e quebravam calado fora dele:

- a pasta do save era montada como `~/AppData/LocalLow/TesseractStudio/TaskbarHero` em qualquer sistema. `platform_support.game_save_dir_candidates` procura os prefixos Proton/Wine no Linux, `Application Support` e garrafas Crossover no macOS, e o caminho histórico no Windows;
- `os.startfile` não existe fora do Windows: "Abrir pasta do save" levantaria `AttributeError`. Agora usa `xdg-open`/`open`/`startfile` conforme o sistema e avisa quando nenhum abridor responde;
- `LOCALAPPDATA` decidia onde gravar cache e ícones no modo empacotado; agora usa `XDG_DATA_HOME` no Linux e `Application Support` no macOS.

Além disso, a fonte `Segoe UI` era pedida por nome fixo em 36 lugares. Ela não existe no Linux nem no macOS, e pedir uma família ausente faz o Tk cair numa fonte bitmap antiga — a interface inteira ficava com aparência de aplicação dos anos 90. A família agora é resolvida em tempo de execução entre as instaladas.

O `HollyEditTBH.spec` empacota nas três plataformas (VERSIONINFO só no Windows, `BUNDLE` .app no macOS, UPX desligado no macOS para não invalidar a assinatura), e o CI compila, testa e faz smoke test do executável em `windows-latest`, `ubuntu-latest` e `macos-latest`.

## Estado da versão

A 3.4.0 corrige defeitos de domínio e remove os acoplamentos frágeis entre as três camadas do editor. O formato do save, AES, derivação de chave, HMAC de `SystemInfo` e a persistência transacional da 3.3.2 permanecem intactos.

O que mudou de comportamento:

- **espaço 6 volta a ser o amuleto.** O núcleo mapeava o prefixo `62` tanto no espaço 6 quanto no 8, de modo que nenhum amuleto era aceito no próprio espaço e um anel parecia válido nos dois. A divergência só não aparecia no produto porque a camada intermediária sobrescrevia a tabela em tempo de importação;
- **gate do Navio de Trocas.** O Mercado só existe com o Cubo no nível 10. O editor lê `cubeSaveLevelData` e diz, na própria janela, se este save já tem acesso — antes ele preparava filas para uma conta que não podia listar nada;
- **uma política de Mercado só.** `MARKET_POLICY_CHECKED_AT` ("12/08/2026") e `POLICY_CHECKED_AT` ("2026-07-06") eram duas datas diferentes exibidas na mesma janela. Agora existe `market_policy.py`;
- **páginas bloqueadas do armazém são reportadas.** Uma página de DLC não comprada devolvia "0 pré-candidato(s) · capacidade disponível atendida", texto que culpava o save pelo que era limitação do destino;
- **espaço sem chave de desbloqueio falha fechado.** Antes a ausência de `IsUnLock` era lida como liberada, e a gravação seguinte marcava a página como desbloqueada no save;
- **ferramenta de moedas comemorativas** (ver seção própria);
- **uma entrada só.** `hollyedittbh_next.py` expunha um `main()` próprio: executá-lo entregava um editor sem persistência transacional, sem detecção fail-safe do jogo aberto e sem os bloqueios de criação/duplicação do Modo Protegido.

A auditoria histórica da 3.3.1 permanece em `AUDITORIA_FINAL_v3.3.1.md` e continua sendo a referência das garantias já conquistadas.

## Moedas comemorativas

As dez *Anniversary Coins* ocupam a faixa 160001-160010, são do tipo MATERIAL e cobrem uma raridade cada, de Comum a Cósmico. Caem de baús, não têm receita e são consumidas na aba **Oferenda** do Cubo, que devolve um equipamento aleatório. Por serem material, negociam no Mercado em qualquer raridade — inclusive Divino e Cósmico, que ficam bloqueados quando são equipamento.

A aba **Moedas** da Central de Inteligência localiza todas as cópias espalhadas pelo inventário e pelo armazém, mostra quantidade e origem por moeda e reúne tudo em uma página escolhida do armazém. A fila:

- move apenas moedas que já existem no save; não cria, duplica, converte nem consome nenhuma;
- ignora as que já estão na página de destino, em vez de gastar espaço trocando um slot por outro;
- ordena da raridade mais alta para a mais baixa, para que o espaço disponível seja ocupado pelas mais valiosas;
- recusa uma página bloqueada e diz que ela está bloqueada;
- passa pela mesma confirmação e pela mesma gravação transacional das demais filas.

A mesma aba também permite **criar** moedas: escolha a moeda, a quantidade e a página do armazém e confirme. Essa ação usa o fluxo genérico de criação de itens do editor (`ProEditor.create_item`) — o mesmo caminho testado e usado pelo restante do editor —, então, ao contrário da fila de reunião acima, ela cria itens de verdade no save. Por isso pede confirmação explícita antes de aplicar, respeita o limite de lote do Modo Protegido e a moeda criada entra na sessão como "criada", ficando fora das filas de pré-candidato a Mercado, igual a qualquer outro item criado pelo editor.

O registro das dez moedas vive em `commemorative_coins.py` e é conferido contra `tbh_items_cache.json` por teste automatizado.

## Recursos principais

- abre e salva `SaveFile_Live.es3` com criptografia e assinatura de integridade;
- cria backup antes de substituir um save previamente carregado;
- prepara o novo save em arquivo temporário no mesmo diretório, executa `flush` + `fsync` e valida SHA-256 antes do commit;
- no Windows, usa `ReplaceFileW` para combinar em uma única chamada nativa a substituição e a captura do conteúdo anterior;
- trata os estados de falha documentados de `ReplaceFileW` e tenta restaurar o caminho principal sem sobrescrever um arquivo concorrente que tenha reaparecido;
- durante rollback, só descarta o arquivo substituído se o SHA-256 provar que ele é o blob gerado pelo editor; uma segunda versão concorrente é preservada para recuperação;
- rejeita e restaura uma versão externa quando o conteúdo substituído não corresponde ao SHA-256 da origem carregada;
- abre, edita e exporta dumps JSON pela interface validada;
- interface em português do Brasil, com contraste, raridade visual, barras de rolagem em todas as tabelas e fluxo guiado;
- retratos próprios para as seis classes de herói;
- busca sem diferença entre acentos/maiúsculas e filtros por raridade e tipo;
- filtros no inventário, armazém, troca, criação e edição de itens;
- encantamentos limitados a equipamentos, espaços e atributos compatíveis;
- **Central de Inteligência** com análise e prévia antes das alterações automáticas;
- pontuação contínua de equipamentos por raridade, nível conhecido, afinidade do herói, tiers e ocupação dos encantamentos;
- perfis de heróis em `hero_profiles.json`, explicitamente heurísticos e calibráveis;
- otimização global dos heróis por alocação exata (`intelligence_engine.optimal_unique_assignment`): um item não é reutilizado, nenhum herói é rebaixado para beneficiar outro e a distribuição maximiza a soma das notas entre todos os heróis ao mesmo tempo — a ordem dos heróis no save não decide um item disputado;
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
- executáveis Windows, Linux e macOS validados por testes, PyInstaller, metadados, smoke test e checksum no GitHub Actions.

## Persistência 3.3.2

A 3.3.1 já gravava por temporário + `fsync` + `os.replace`, mas a verificação de alteração externa era feita na camada de interface antes da persistência. Isso deixava uma janela curta entre a conferência e a substituição efetiva.

Na 3.3.2, `VerifiedSaveFile` registra o SHA-256 dos bytes exatos carregados. Antes da gravação, o novo blob é gerado em temporário e validado. No Windows, `ReplaceFileW` combina em uma única função as etapas de substituição e pode gerar simultaneamente uma cópia do arquivo substituído. O hash dessa cópia é então comparado com a origem esperada:

- se coincidir, o commit é aceito e o fingerprint interno é atualizado;
- se divergir, a versão externa capturada é restaurada e o novo blob é rejeitado;
- se a troca falhar antes de alterar o caminho, o original permanece no lugar;
- se `ReplaceFileW` retornar um estado documentado em que o original já foi movido para o backup e o caminho principal ficou ausente, a camada tenta restaurar o original sem substituir qualquer arquivo que tenha reaparecido;
- se outra gravação externa ocorrer durante a tentativa de rollback, essa segunda versão é capturada, validada como conteúdo não pertencente ao editor e preservada em arquivo de recuperação em vez de ser apagada;
- se ocorrer uma condição excepcional após a troca e a restauração automática não puder ser confirmada, a cópia capturada é preservada e não é apagada silenciosamente.

As garantias de recuperação descritas acima dependem de `ReplaceFileW` e são validadas no runner Windows. Fora do Windows a gravação continua sendo por temporário + `fsync` + `os.replace` com validação de SHA-256, mas a captura do conteúdo substituído não acontece em uma única chamada nativa: uma escrita externa entre o `copy2` e o `os.replace` pode escapar dessa proteção. O editor funciona nas três plataformas; esta diferença específica de janela de corrida permanece.

## Modo Protegido

O Modo Protegido permanece ativo por padrão e mantém todas as barreiras da 3.3.1:

- não cria itens inexistentes no save carregado;
- não duplica itens;
- não equipa itens criados durante a sessão;
- itens modificados/criados continuam excluídos da inteligência de Mercado;
- bloqueia salvamento enquanto o Taskbar Hero estiver aberto;
- bloqueia salvamento quando o conteúdo do arquivo mudou no disco depois de ser carregado;
- na 3.3.2, também bloqueia se a assinatura inicial do save não puder ser obtida;
- na 3.3.2, falha/timeout/retorno inválido do `tasklist` é tratado conservadoramente como estado inseguro, em vez de presumir que o jogo está fechado;
- a detecção executa `%SystemRoot%\System32\tasklist.exe` por caminho absoluto, evitando resolução pelo diretório da aplicação ou pelo `PATH`, e usa decodificação tolerante sem afetar a comparação ASCII do processo.

A criação e duplicação local continuam disponíveis somente após desativação consciente do Modo Protegido. Isso não transforma a operação em segura ou aceita pelo jogo.

## Mercado Steam

Toda a política vive em `market_policy.py` e é conferida por teste. Regras públicas na data de `POLICY_CHECKED_AT`:

- o **Navio de Trocas**, dentro do Cubo, é a única porta entre o save e o inventário Steam, e abre no **Cubo nível 10**;
- equipamento negocia **a partir de Lendário**: Comum, Incomum e Raro foram retirados do Mercado;
- equipamento **Celestial, Divino e Cósmico** segue restrito, com exceção conhecida para Soulstones;
- **material negocia em qualquer raridade** — é por isso que as moedas comemorativas entram mesmo sendo Cósmicas;
- a conta precisa de **Steam Guard** ativo para listar.

A política conservadora da 3.3.1 foi preservada:

- 4 slots por rodada por padrão;
- itens criados ou modificados pelo editor ficam fora da inteligência de Mercado;
- encantamentos não aumentam artificialmente a prioridade de venda;
- quantidade de anúncios concorrentes não é tratada como prova de liquidez;
- snapshot completo anterior prevalece sobre nova coleta parcial;
- o editor não acessa login, cookies privados ou inventário autenticado da Steam;
- não envia itens à Steam e não promete elegibilidade, preço, venda ou demanda.

A coleta pública tinha duas implementações quase idênticas — `market_intelligence.fetch_market_snapshot` e a versão protegida de `market_snapshot_guard` — com semânticas divergentes de `complete` e User-Agents diferentes (`HollyEditTBH/3.x` contra `APP_VERSION`). A versão protegida virou a única implementação; `market_snapshot_guard` permanece apenas como nome estável.

Para contas que efetivamente disponham de mais slots, o limite técnico pode ser ajustado pela variável de ambiente `HOLLYEDIT_MARKET_SLOTS`, entre 1 e 12.

## Instalar e executar

Requisitos: **Python 3.12** com Tk e a biblioteca `cryptography`.

```bash
# Windows
py -3.12 -m pip install cryptography
py -3.12 hollyedittbh_final.py

# Linux (Debian/Ubuntu — o Tk vem em pacote separado)
sudo apt-get install python3-tk
python3.12 -m pip install cryptography
python3.12 hollyedittbh_final.py

# macOS (o python.org e o Homebrew já trazem o Tk)
python3.12 -m pip install cryptography
python3.12 hollyedittbh_final.py
```

O editor localiza sozinho a pasta do save de cada sistema. No Linux e no macOS o Taskbar Hero roda sob Proton/Wine ou Crossover, e o save fica dentro do prefixo — se ele estiver em outro lugar, use **Abrir save** e aponte o `.es3` manualmente.

## Entrada oficial do código-fonte

A entrada suportada é `hollyedittbh_final.py`.

`hollyedittbh_next.py` e `legacy_editor.py` são camadas internas, não aplicações: executá-las diretamente é recusado com uma mensagem apontando a entrada suportada. `tbh_save_editor.py` permanece apenas como ponte de compatibilidade: importações resolvem para o núcleo legado e execução direta redireciona para `hollyedittbh_final.py`. O `HollyEditTBH.spec` continua empacotando a entrada final; não existem duas aplicações independentes.

## Testes

Executar a mesma suíte usada pelo CI:

```bash
python3.12 -m unittest -v test_hollyedittbh.py test_intelligence_v33.py test_market_ranking_v33.py test_hero_profiles_v33.py test_final_audit_v331.py test_hardening_v332.py test_v340_coins_and_policy.py test_v341_ux_and_portability.py
```

No Linux sem sessão gráfica, prefixe com `xvfb-run -a`: cinco testes exercitam widgets Tk de verdade e são pulados quando não há display.

A suíte contém **165 testes automatizados**. Os 132 anteriores cobrem o registro das moedas comemorativas conferido contra o catálogo, o plano de consolidação (ordem por raridade, espaço restrito, página bloqueada, idempotência), o gate do Cubo nível 10, a política de Mercado como definição única, a compatibilidade do espaço do amuleto, o desbloqueio de espaço falhando fechado, os resumos de fila que separam "sem candidato" de "sem espaço", e a ausência dos hacks removidos.

As 33 regressões novas (`test_v341_ux_and_portability.py`) cobrem os defeitos de interface e portabilidade: comandos sem chamador (uma guarda genérica varre todos os `open_*` e falha se algum ficar órfão), acentuação de todos os literais de interface, o rótulo de herói em português, o destino acentuado na barra de status, a recusa de execução direta do núcleo, cada camada declarando o algoritmo que roda, as contagens e confirmações das operações em massa, os caminhos de save das três plataformas, a abertura de pasta sem `os.startfile`, a resolução de fonte, os marcadores de plataforma no `requirements-build.txt`, os três runners no CI e as barras de rolagem — incluindo a ordem de empilhamento, porque a tabela é irmã do próprio container de rolagem e sem `lift` fica invisível apesar de continuar populada, a reserva da faixa de ações antes da área expansível e a rolagem da aba mais alta que a janela.

Dois testes do baseline só passavam em um host Windows com o jogo instalado; agora exercitam o comportamento pretendido em qualquer plataforma.

O CI também executa:

- `python -m compileall -q .`;
- smoke test de 3 segundos da ponte `tbh_save_editor.py`;
- instalação da toolchain fixada em `requirements-build.txt`;
- build pelo PyInstaller;
- conferência exata de `FileVersion` e `ProductVersion` 3.4.0/3.4.0.0 (Windows);
- inicialização real do executável por 5 a 8 segundos em cada plataforma;
- geração de `SHA256SUMS.txt`;
- validação de que `dist` contém somente `HollyEditTBH.exe` e `SHA256SUMS.txt` (Windows);
- conferência do layout do bundle `.app` e do `CFBundleShortVersionString` (macOS);
- publicação de um artefato por plataforma.

As Actions externas continuam fixadas aos SHAs auditados de `actions/checkout v7.0.1`, `actions/setup-python v7.0.0` e `actions/upload-artifact v7.0.1`, com `permissions: contents: read`. O Python do CI é **3.12.10** e as dependências de empacotamento usadas pelo build estão explicitamente fixadas em `requirements-build.txt`.

## Gerar o executável

O mesmo comando serve as três plataformas; o `.spec` decide o que é específico de cada uma.

```bash
python3.12 -m pip install -r requirements-build.txt
python3.12 -m PyInstaller --noconfirm --clean HollyEditTBH.spec
```

Saída esperada:

```text
Windows   dist/HollyEditTBH.exe
Linux     dist/HollyEditTBH
macOS     dist/HollyEditTBH.app
```

O recurso VERSIONINFO só é aplicado no Windows, e o UPX fica desligado no macOS porque comprimir o executável invalida a assinatura de código e o Gatekeeper recusa abrir o resultado. O bundle macOS não é assinado nem notarizado por esta mudança (ver *Distribuição e decisões do mantenedor*).

## Verificação do pacote

O GitHub Actions publica um artefato por plataforma, cada um com o executável e o `SHA256SUMS.txt` correspondente. O checksum deve ser conferido a partir do arquivo pertencente ao **mesmo build**, pois o empacotamento PyInstaller não é tratado como byte a byte reprodutível entre execuções independentes.

## Distribuição e decisões do mantenedor

Três itens permanecem deliberadamente fora de automação nesta revisão:

- **Assinatura digital do executável (e notarização no macOS):** tecnicamente recomendável, mas depende de certificado/chave privada e de política de custódia de segredo. Nenhum certificado foi inventado ou incluído no repositório.
- **GitHub Release/tag:** pode ser automatizado no futuro após merge por workflow separado e permissões mínimas, mas a 3.4.0 não publica release automaticamente. O repositório continua sem release/tag criado por esta mudança.
- **Licença:** o repositório não recebe uma licença por decisão automática. A escolha da licença é decisão jurídica/do proprietário e deve ser feita expressamente pelo mantenedor.

## Atalhos

- `Ctrl+O`: abrir save;
- `Ctrl+S`: salvar alterações;
- `Ctrl+Shift+E`: exportar JSON.

## Limites

Nenhum editor de save pode oferecer garantia contra sanções, incompatibilidade futura ou mudança de regras do servidor. O Modo Protegido reduz alterações acidentais e separa operações de maior risco; não oculta modificações nem contorna sistemas de detecção.
