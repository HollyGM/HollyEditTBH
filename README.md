# HollyEditTBH

Editor independente e não oficial de saves do **TBH: Task Bar Hero**, para **Windows, Linux e macOS**.

Projeto: <https://github.com/HollyGM/HollyEditTBH> · Versão atual: **3.4.0**

O editor abre o `SaveFile_Live.es3` do jogo, mostra heróis, itens e progresso em português, e grava de volta com backup e validação de integridade. O **Modo Protegido** vem ligado por padrão e bloqueia as operações de maior risco. Leia [Limites](#limites) antes de usar: nenhum editor de save oferece garantia contra sanções do jogo ou da Steam.

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

Quem prefere executável pronto encontra um pacote por plataforma nos artefatos do GitHub Actions, que exigem conta no GitHub e expiram 30 dias após o build — veja [Gerar o executável](#gerar-o-executável) e [Verificação do pacote](#verificação-do-pacote).

O editor localiza sozinho a pasta do save de cada sistema e, se encontrar o `SaveFile_Live.es3`, já o abre ao iniciar. No Windows ela fica em `AppData/LocalLow/TesseractStudio/TaskbarHero`; no Linux e no macOS o Taskbar Hero roda sob Proton, Wine ou Crossover, e a mesma árvore vive dentro do prefixo.

No Linux, a procura não se limita às pastas dentro do `$HOME`: as bibliotecas Steam declaradas em `libraryfolders.vdf` também entram, de modo que uma biblioteca em disco externo — configuração comum de quem tem SSD de sistema pequeno — é encontrada. Se o save estiver em outro lugar, use **Abrir save** e aponte o `.es3` manualmente.

Passar um caminho na linha de comando ou deixar um `player_dump.json` ao lado do programa continua tendo precedência sobre a abertura automática.

Feche o jogo antes de salvar. No Windows, o Modo Protegido detecta o Taskbar Hero em execução e recusa gravar; no Linux e no macOS essa detecção não existe, então fechar o jogo antes de salvar é responsabilidade sua.

### Atalhos

- `Ctrl+O`: abrir save;
- `Ctrl+S`: salvar alterações;
- `Ctrl+Shift+E`: exportar JSON.

## O que o editor faz

**Arquivo e integridade**

- abre e salva `SaveFile_Live.es3` com criptografia e assinatura de integridade;
- cria backup antes de substituir um save previamente carregado;
- prepara o novo save em arquivo temporário no mesmo diretório, executa `flush` + `fsync` e valida SHA-256 antes do commit;
- assinatura local por tamanho, timestamp e SHA-256 do conteúdo, para detectar alteração externa mesmo com tamanho e horário preservados;
- abre, edita e exporta dumps JSON pela interface validada.

**Interface**

- português do Brasil, com contraste, raridade visual, barras de rolagem em todas as tabelas e fluxo guiado;
- o cabeçalho de detalhe diz **o que** está sendo editado e **de onde** vem (`Onde está: Inventário - espaço 1 · ID único 1001`), e destaca itens sem local no save;
- o painel de equipamentos identifica o herói ativo acima dos dez espaços;
- retratos próprios para as seis classes de herói;
- busca sem diferença entre acentos e maiúsculas, com filtros por raridade e tipo no inventário, armazém, trocas, criação e edição;
- a família de fonte é escolhida entre as instaladas no sistema, em vez de pedir uma família fixa que não existe fora do Windows.

**Edição**

- encantamentos limitados a equipamentos, espaços e atributos compatíveis;
- compatibilidade correta para amuleto, brinco, anel e abraçadeira;
- operações em massa (definir um campo em toda uma coleção, desbloquear pets) pedem confirmação, informam quantos registros serão realmente alcançados e não sujam o save quando não há nada a alterar;
- validação estrutural com reparo conservador.

**Central de Inteligência**

Um assistente que **primeiro analisa, depois mostra a prévia e só altera o save com confirmação**. Nada é gravado em disco até você usar *Salvar alterações*. Sete abas:

| Aba | O que faz |
| --- | --- |
| **Começar** | estado do save, do jogo e a ordem das etapas |
| **Equipamentos** | compara o item equipado com a melhor opção que você já possui, herói a herói ou todos de uma vez |
| **Desbloqueios** | libera tutoriais, heróis, pets, grupos de atributos e receitas já conhecidas pela versão do save |
| **Mercado** | separa pré-candidatos a venda entre itens existentes e não modificados |
| **Reciclagem** | encontra equipamentos duplicados e preserva a melhor cópia |
| **Moedas** | reúne as moedas comemorativas espalhadas pelo save, ou cria moedas novas |
| **Segurança** | o que cada proteção faz e o que ela não promete |

A pontuação de equipamentos é contínua e combina raridade, nível conhecido, afinidade do herói, tiers e ocupação dos encantamentos. Os perfis de herói vivem em `hero_profiles.json` e são explicitamente heurísticos e calibráveis.

A **otimização global dos heróis** usa alocação exata (`intelligence_engine.optimal_unique_assignment`): um item não é reutilizado, nenhum herói é rebaixado para beneficiar outro, e a distribuição maximiza a soma das notas entre todos os heróis ao mesmo tempo — a ordem dos heróis no save não decide um item disputado.

O catálogo de itens se atualiza sozinho, com validação contra respostas parciais e regressões abruptas. O Steam Community Market entra apenas como snapshot público e cacheado, usado como referência de preço.

## Moedas comemorativas

As dez *Anniversary Coins* ocupam a faixa 160001-160010, são do tipo MATERIAL e cobrem uma raridade cada, de Comum a Cósmico. Caem de baús, não têm receita e são consumidas na aba **Oferenda** do Cubo, que devolve um equipamento aleatório. Por serem material, negociam no Mercado em qualquer raridade — inclusive Divino e Cósmico, que ficam bloqueados quando são equipamento.

A aba **Moedas** localiza todas as cópias espalhadas pelo inventário e pelo armazém, mostra quantidade e origem por moeda e reúne tudo em uma página escolhida do armazém. A fila:

- move apenas moedas que já existem no save; não cria, duplica, converte nem consome nenhuma;
- ignora as que já estão na página de destino, em vez de gastar espaço trocando um slot por outro;
- ordena da raridade mais alta para a mais baixa, para que o espaço disponível seja ocupado pelas mais valiosas;
- recusa uma página bloqueada e diz que ela está bloqueada;
- passa pela mesma confirmação e pela mesma gravação transacional das demais filas.

A mesma aba também permite **criar** moedas: escolha a moeda, a quantidade e a página do armazém e confirme. Essa ação usa o fluxo genérico de criação de itens do editor (`ProEditor.create_item`) — o mesmo caminho testado e usado pelo restante do editor —, então, ao contrário da fila de reunião acima, ela cria itens de verdade no save. Por isso pede confirmação explícita antes de aplicar, respeita o limite de lote do Modo Protegido e a moeda criada entra na sessão como "criada", ficando fora das filas de pré-candidato a Mercado, igual a qualquer outro item criado pelo editor.

O registro das dez moedas vive em `commemorative_coins.py` e é conferido contra `tbh_items_cache.json` por teste automatizado.

## Modo Protegido

O Modo Protegido permanece ativo por padrão e mantém todas as barreiras da 3.3.1:

- não cria itens inexistentes no save carregado;
- não duplica itens;
- não equipa itens criados durante a sessão;
- itens modificados/criados continuam excluídos da inteligência de Mercado;
- bloqueia salvamento enquanto o Taskbar Hero estiver aberto;
- bloqueia salvamento quando o conteúdo do arquivo mudou no disco depois de ser carregado;
- bloqueia também se a assinatura inicial do save não puder ser obtida;
- falha, timeout ou retorno inválido do `tasklist` é tratado conservadoramente como estado inseguro, em vez de presumir que o jogo está fechado;
- a detecção executa `%SystemRoot%\System32\tasklist.exe` por caminho absoluto, evitando resolução pelo diretório da aplicação ou pelo `PATH`, e usa decodificação tolerante sem afetar a comparação ASCII do processo.

**Detecção do jogo aberto é exclusiva do Windows.** Fora dele não existe equivalente implementado e a checagem reporta "jogo fechado", de modo que o bloqueio por jogo em execução não protege no Linux nem no macOS. Todas as demais barreiras do Modo Protegido — inclusive o bloqueio por mudança externa do arquivo, que é a proteção mais importante contra perda de progresso — valem nas três plataformas.

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

## Persistência e recuperação

A 3.3.1 já gravava por temporário + `fsync` + `os.replace`, mas a verificação de alteração externa era feita na camada de interface antes da persistência. Isso deixava uma janela curta entre a conferência e a substituição efetiva.

Desde a 3.3.2, `VerifiedSaveFile` registra o SHA-256 dos bytes exatos carregados. Antes da gravação, o novo blob é gerado em temporário e validado. No Windows, `ReplaceFileW` combina em uma única função as etapas de substituição e pode gerar simultaneamente uma cópia do arquivo substituído. O hash dessa cópia é então comparado com a origem esperada:

- se coincidir, o commit é aceito e o fingerprint interno é atualizado;
- se divergir, a versão externa capturada é restaurada e o novo blob é rejeitado;
- se a troca falhar antes de alterar o caminho, o original permanece no lugar;
- se `ReplaceFileW` retornar um estado documentado em que o original já foi movido para o backup e o caminho principal ficou ausente, a camada tenta restaurar o original sem substituir qualquer arquivo que tenha reaparecido;
- se outra gravação externa ocorrer durante a tentativa de rollback, essa segunda versão é capturada, validada como conteúdo não pertencente ao editor e preservada em arquivo de recuperação em vez de ser apagada;
- se ocorrer uma condição excepcional após a troca e a restauração automática não puder ser confirmada, a cópia capturada é preservada e não é apagada silenciosamente.

Em qualquer falha de persistência o estado de `integrity_valid` é restaurado ao valor anterior, para que um erro de gravação não deixe o save carregado marcado como íntegro sem ter sido gravado.

**Diferença entre plataformas.** As garantias de recuperação acima dependem de `ReplaceFileW` e são validadas no runner Windows. Fora do Windows a gravação continua sendo por temporário + `fsync` + `os.replace` com validação de SHA-256, mas a captura do conteúdo substituído não acontece em uma única chamada nativa: uma escrita externa entre o `copy2` e o `os.replace` pode escapar dessa proteção. O editor funciona nas três plataformas; esta diferença específica de janela de corrida permanece.

## Limites

Nenhum editor de save pode oferecer garantia contra sanções, incompatibilidade futura ou mudança de regras do servidor. O Modo Protegido reduz alterações acidentais e separa operações de maior risco; não oculta modificações nem contorna sistemas de detecção.

O desenvolvedor do jogo informa que itens criados ou obtidos por métodos anormais podem resultar em restrição do jogo ou do Mercado. O editor não oferece proteção contra essa verificação, e a elegibilidade de venda é decidida pelo jogo e pela Steam, não por este programa.

---

# Para quem desenvolve

## Entrada oficial do código-fonte

A entrada suportada é `hollyedittbh_final.py`.

`hollyedittbh_next.py` e `legacy_editor.py` são camadas internas, não aplicações: executá-las diretamente é recusado com uma mensagem apontando a entrada suportada. `tbh_save_editor.py` permanece apenas como ponte de compatibilidade: importações resolvem para o núcleo legado e execução direta redireciona para `hollyedittbh_final.py`. O `HollyEditTBH.spec` continua empacotando a entrada final; não existem duas aplicações independentes.

Módulos de apoio sem dependência de `tkinter`, para poderem ser testados sem interface: `intelligence_engine.py` (pontuação e alocação), `market_policy.py` (política única de Mercado), `commemorative_coins.py` (registro e plano das moedas), `safe_persistence.py` (gravação transacional), `platform_support.py` (caminhos, abertura de pastas e fonte por sistema).

`app_meta.py` concentra os metadados de identidade — nome, versão e o AppID Steam do jogo. O AppID chegou a existir duas vezes com valores diferentes, o que quebrou a descoberta do save no Linux; ele agora tem uma definição só, e um teste falha se um módulo voltar a redefini-lo.

## Testes

Executar a mesma suíte usada pelo CI:

```bash
python3.12 -m unittest -v test_hollyedittbh.py test_intelligence_v33.py test_market_ranking_v33.py test_hero_profiles_v33.py test_final_audit_v331.py test_hardening_v332.py test_v340_coins_and_policy.py test_v341_ux_and_portability.py test_v342_stash_geometry.py
```

No Linux sem sessão gráfica, prefixe com `xvfb-run -a`: cinco testes exercitam widgets Tk de verdade e são pulados quando não há display.

A suíte contém **200 testes automatizados**:

| Módulo | Testes | Cobre |
| --- | ---: | --- |
| `test_hollyedittbh.py` | 30 | núcleo do editor, filtros, criptografia e diálogo de abertura |
| `test_intelligence_v33.py` | 13 | pontuação contínua, alocação exata e prefixos de espaço |
| `test_market_ranking_v33.py` | 2 | ordenação da fila de Mercado |
| `test_hero_profiles_v33.py` | 7 | integridade dos perfis de herói |
| `test_final_audit_v331.py` | 14 | auditoria da 3.3.1 |
| `test_hardening_v332.py` | 19 | persistência transacional, conflito, rollback e gates de build |
| `test_v340_coins_and_policy.py` | 48 | moedas comemorativas, política única de Mercado, gate do Cubo, espaço do amuleto |
| `test_v341_ux_and_portability.py` | 49 | interface, português, portabilidade e descoberta do save |
| `test_v342_stash_geometry.py` | 18 | tamanho e número das abas do armazém, conferidos contra a tela do jogo, e itens fora delas |

Alguns destaques do que a suíte protege, por serem defeitos que já ocorreram neste projeto:

- **comandos órfãos** — uma guarda genérica varre todos os `open_*` e falha se algum ficar sem chamador, como aconteceu com a otimização global;
- **acentuação** — todos os literais de interface são percorridos, e um texto novo que perca o acento reprova;
- **cada camada declara o algoritmo que roda**, para a prévia não descrever a estratégia da outra;
- **ordem de empilhamento das tabelas** — a tabela é irmã do próprio container de rolagem e, sem `lift`, fica invisível apesar de continuar populada;
- **reserva da faixa de ações** antes da área expansível, e rolagem de uma aba mais alta que a janela;
- **caminhos de save das três plataformas**, abertura de pasta sem `os.startfile` e resolução de fonte;
- **descoberta do save no Linux** — AppID com definição única, bibliotecas Steam em disco externo, VDF ausente ou corrompido, e precedência do jogo publicado sobre o playtest.

Dois testes do baseline só passavam em um host Windows com o jogo instalado; hoje exercitam o comportamento pretendido em qualquer plataforma.

O CI também executa, nos três sistemas:

- `python -m compileall -q .`;
- smoke test de 3 segundos da ponte `tbh_save_editor.py` (Windows);
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

O recurso VERSIONINFO só é aplicado no Windows, e o UPX fica desligado no macOS porque comprimir o executável invalida a assinatura de código e o Gatekeeper recusa abrir o resultado. O bundle macOS não é assinado nem notarizado (ver *Distribuição e decisões do mantenedor*).

## Verificação do pacote

O GitHub Actions publica um artefato por plataforma, cada um com o executável e o `SHA256SUMS.txt` correspondente. O checksum deve ser conferido a partir do arquivo pertencente ao **mesmo build**, pois o empacotamento PyInstaller não é tratado como byte a byte reprodutível entre execuções independentes.

## Histórico

### 3.4.0 — interface, português e portabilidade

Auditoria da interface. Nenhum destes defeitos altera o formato do save, e nenhuma correção tocou AES, derivação de chave, HMAC de `SystemInfo` ou a persistência transacional.

*Funções que não funcionavam*

- **a otimização global de heróis era código morto.** `open_auto_equip_all_preview` — o único caminho que usa a alocação exata de `intelligence_engine.optimal_unique_assignment` — não tinha nenhum chamador em lugar nenhum do programa. O recurso estava implementado e testado, mas era inacessível pela interface. Ganhou entrada no painel de heróis (**Otimizar todos os heróis**) e na aba **Equipamentos** da Central de Inteligência;
- **a prévia dessa otimização descrevia o algoritmo errado.** O texto dizia "a ordem dos heróis decide quem fica com um item disputado — não é um ótimo global", que descreve a versão gulosa do núcleo legado, enquanto o produto sempre roda a camada intermediária, que resolve o ótimo exato. Cada camada passou a declarar o próprio critério (`auto_equip_all_strategy_note`);
- **`legacy_editor.py` abria o editor ao ser executado direto**, entregando um editor sem persistência transacional, sem detecção fail-safe do jogo aberto e sem os bloqueios do Modo Protegido — apesar de a documentação já afirmar que ele recusava, como `hollyedittbh_next.py`;
- **nenhuma tabela tinha barra de rolagem.** As 462 posições do armazém e os milhares de registros da aba "Todos os itens" só podiam ser percorridos pela roda do mouse, sem indicação de quanto havia abaixo;
- **"Definir em todos" aplicava sem confirmação e errava a contagem.** Era a única operação em massa sem confirmação, e o resumo dizia "atualizado em N registros" contando também os registros que não possuem o campo;
- **"Desbloquear pets" marcava o save como alterado mesmo sem alterar nada**;
- **falhas de rede apareciam como exceção crua** na barra de status, o que parece defeito do programa em vez de ausência de internet;
- **em telas de 1366x768 a faixa de ações saía da janela.** O `pack` aloca por ordem e a área expansível era empacotada primeiro, consumindo toda a cavidade; a aba Moedas deixava o próprio botão principal inalcançável.

*Exibição*

- o cabeçalho de detalhe mostrava o que estava sendo editado, mas nunca **de onde**; passou a exibir o local do item e a avisar em destaque quando ele não tem local no save;
- o painel de equipamentos mostrava dez cartões sem dizer de quem eram; passou a trazer nome e nível do herói ativo;
- a prévia da otimização global passou a mostrar a origem de cada item recomendado;
- diálogos que ignoravam a adaptação de tela (`configure_dialog`) foram padronizados, e todos passaram a ser modais com fechamento por `Esc`.

*Português*

Cerca de 40 mensagens visíveis estavam sem acento — "copia", "sao", "automatico", "excluido", "Alocacao automatica concluida", "Reparacao concluida", "Informacoes", "colecao" —, duas listas de locais rotulavam um herói desconhecido como `Hero 101`, e a barra de status exibia o valor interno `Armazem 3` em vez de `Armazém 3`.

*Portabilidade*

Três pontos assumiam Windows e quebravam calado fora dele:

- a pasta do save era montada como `~/AppData/LocalLow/TesseractStudio/TaskbarHero` em qualquer sistema. `platform_support.game_save_dir_candidates` passou a procurar os prefixos Proton/Wine no Linux, `Application Support` e garrafas Crossover no macOS, e o caminho histórico no Windows;
- `os.startfile` não existe fora do Windows: "Abrir pasta do save" levantaria `AttributeError`. Passou a usar `xdg-open`/`open`/`startfile` conforme o sistema, avisando quando nenhum abridor responde;
- `LOCALAPPDATA` decidia onde gravar cache e ícones no modo empacotado; passou a usar `XDG_DATA_HOME` no Linux e `Application Support` no macOS.

Além disso, a fonte `Segoe UI` era pedida por nome fixo em 36 lugares. Ela não existe no Linux nem no macOS, e pedir uma família ausente faz o Tk cair numa fonte bitmap antiga. A família passou a ser resolvida em tempo de execução entre as instaladas.

O `HollyEditTBH.spec` passou a empacotar nas três plataformas (VERSIONINFO só no Windows, `BUNDLE` .app no macOS, UPX desligado no macOS para não invalidar a assinatura), as dependências exclusivas do Windows ganharam marcador de plataforma, e o CI compila, testa e faz smoke test do executável em `windows-latest`, `ubuntu-latest` e `macos-latest`.

### 3.4.0 — geometria do armazém

O editor calculava a página do armazém com **66 espaços**. O jogo usa **49** (grade 7×7). Duas consequências, ambas confirmadas contra um save real cujas abas 1, 2 e 3 tinham 0, 13 e 15 itens — números que batem com 49 e não com 66:

- **os rótulos de página ficavam deslocados.** A "Armazém 3" do editor caía no meio da aba 4 do jogo, então escolher um destino nas filas mandava o item para uma aba diferente da anunciada;
- **o editor gravava fora do alcance do jogo.** Achando que a faixa útil ia até o índice 461, ele escrevia acima de 342, que é o último espaço exibido nas 7 abas. O item ficava íntegro no save e invisível no jogo, sem aviso nenhum. No save examinado eram 26 itens presos assim.

O validador passou a reportar cada item nessa faixa, e **Reparar** os traz de volta para espaços visíveis — só o índice do espaço muda, nada é criado nem apagado.

Nenhum teste pegava isso porque toda a suíte montava os saves sintéticos com o mesmo 66 do produto: fixture e código concordavam no erro. As fixtures passaram a derivar a geometria de `STASH_PAGE_SIZE`.

Uma revisão posterior tentou substituir o `STASH_PAGE_COUNT = 7` por uma medida tirada do próprio save — `stashSaveDatas` traz 528 espaços, todos com `IsUnLock` verdadeiro, o que dá 11 páginas de 49 — e foi revertida. O raciocínio partia de que os itens acima do índice 342 num save antigo teriam sido postos pelo jogo; não foram. Aquele save já continha os itens de `ItemGetSourceType 0`, que são os criados por editor, e os índices ocupados (361-378 e 419-426) caem justamente na faixa que a versão de 66 espaços alcançava. Captura da tela do jogo confirma sete abas numeradas de 1 a 7 e a grade 7×7, com ocupação idêntica à do save: aba 1 vazia, aba 2 com 13, abas 5, 6 e 7 cheias com 49.

Os 528 espaços do vetor são folga, não aba escondida. `GameScreenGeometryTests` fixa os números vindos da tela e falha se alguém voltar a derivá-los de `len(stashSaveDatas)`.

### 3.4.0 — descoberta do save no Linux

O editor não encontrava o save numa instalação Linux comum. Eram dois defeitos independentes, cada um suficiente sozinho para impedir a detecção:

- **AppID errado e duplicado.** `platform_support` procurava `compatdata/2957000`, que é o AppID do playtest, enquanto o valor do jogo publicado (3678970) já existia em `market_policy`. Duas constantes homônimas com valores conflitantes, contra o padrão de fonte única do projeto. O AppID passou a viver em `app_meta.py`; os dois módulos importam de lá, e a procura considera os dois prefixos, com o jogo publicado à frente do playtest.
- **Só bibliotecas Steam dentro do `$HOME`.** O Steam registra bibliotecas secundárias em `libraryfolders.vdf`, que o editor não lia. Quem tem SSD de sistema pequeno e joga a partir de outro disco continuava sem detecção mesmo com o AppID corrigido. A leitura é feita por expressão regular sobre as linhas `"path"`, sem dependência nova, e nunca levanta exceção — `legacy_editor` resolve `GAME_SAVE_DIR` em tempo de import, então um disco desmontado ou um VDF corrompido derrubaria a aplicação na inicialização.

Achar o caminho, porém, ainda não abria o save: `main` carregava apenas um argumento de linha de comando ou um `player_dump.json`, e `DEFAULT_SAVE_FILE` só escolhia a pasta inicial do seletor. O `SaveFile_Live.es3` encontrado passou a ser aberto na inicialização, atrás dessas duas precedências.

### 3.4.0 — correções de domínio

Remoção dos acoplamentos frágeis entre as três camadas do editor:

- **espaço 6 volta a ser o amuleto.** O núcleo mapeava o prefixo `62` tanto no espaço 6 quanto no 8, de modo que nenhum amuleto era aceito no próprio espaço e um anel parecia válido nos dois. A divergência só não aparecia no produto porque a camada intermediária sobrescrevia a tabela em tempo de importação;
- **gate do Navio de Trocas.** O Mercado só existe com o Cubo no nível 10. O editor lê `cubeSaveLevelData` e diz, na própria janela, se este save já tem acesso — antes ele preparava filas para uma conta que não podia listar nada;
- **uma política de Mercado só.** `MARKET_POLICY_CHECKED_AT` ("12/08/2026") e `POLICY_CHECKED_AT` ("2026-07-06") eram duas datas diferentes exibidas na mesma janela. Passou a existir `market_policy.py`;
- **páginas bloqueadas do armazém são reportadas.** Uma página de DLC não comprada devolvia "0 pré-candidato(s) · capacidade disponível atendida", texto que culpava o save pelo que era limitação do destino;
- **espaço sem chave de desbloqueio falha fechado.** Antes a ausência de `IsUnLock` era lida como liberada, e a gravação seguinte marcava a página como desbloqueada no save;
- **ferramenta de moedas comemorativas** (ver seção própria);
- **uma entrada só.** `hollyedittbh_next.py` expunha um `main()` próprio: executá-lo entregava um editor sem persistência transacional, sem detecção fail-safe do jogo aberto e sem os bloqueios de criação/duplicação do Modo Protegido.

### 3.3.2 e anteriores

A persistência transacional descrita em [Persistência e recuperação](#persistência-e-recuperação) chegou na 3.3.2. A auditoria histórica da 3.3.1 permanece em `AUDITORIA_FINAL_v3.3.1.md` e continua sendo a referência das garantias já conquistadas.

## Distribuição e decisões do mantenedor

Três itens permanecem deliberadamente fora de automação:

- **Assinatura digital do executável (e notarização no macOS):** tecnicamente recomendável, mas depende de certificado/chave privada e de política de custódia de segredo. Nenhum certificado foi inventado ou incluído no repositório. Sem isso, o SmartScreen no Windows e o Gatekeeper no macOS vão pedir confirmação do usuário na primeira abertura.
- **GitHub Release/tag:** pode ser automatizado no futuro por workflow separado e permissões mínimas. O repositório não publica release automaticamente; os pacotes ficam nos artefatos do Actions.
- **Licença:** o repositório não recebe uma licença por decisão automática. A escolha da licença é decisão jurídica/do proprietário e deve ser feita expressamente pelo mantenedor. Sem ela, o padrão legal é "todos os direitos reservados", o que impede terceiros de redistribuir ou contribuir com segurança.
