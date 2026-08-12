# Auditoria final — HollyEditTBH 3.3.1

Data: 12/08/2026

## Conclusão

A versão 3.3.1 encerra a auditoria técnica do HollyEditTBH com foco em consistência de distribuição, proteção operacional, integridade do save, inteligência de equipamentos, Mercado Steam, atualização de catálogo, documentação e build Windows.

O candidato foi validado em Windows Server 2025 com Python 3.12.10 e PyInstaller 6.22.0.

Resultado dos gates de release:

- **55/55 testes automatizados aprovados**;
- `python -m compileall -q .` aprovado;
- execução direta da ponte histórica `tbh_save_editor.py` mantida ativa por 3 segundos e redirecionada para a aplicação final;
- build PyInstaller concluído pela entrada `hollyedittbh_final.py`;
- `FileVersion` confirmada como **3.3.1**;
- `HollyEditTBH.exe` iniciado e mantido ativo por 5 segundos no smoke test;
- `SHA256SUMS.txt` gerado e publicado no mesmo artefato do executável.

### Rastreabilidade do binário

O SHA-256 não é fixado neste relatório porque o executável empacotado pelo PyInstaller não se mostrou reprodutível byte a byte entre execuções equivalentes do CI. A fonte de verdade para cada pacote é o `SHA256SUMS.txt` publicado **no mesmo artefato do commit exato que gerou o executável**. Essa escolha evita registrar no repositório um digest que se torna obsoleto no build seguinte.

## Escopo auditado

Foram revisados:

- leitura, descriptografia, serialização, HMAC e gravação do `.es3`;
- backup, `fsync` e substituição atômica do save;
- detecção de mudança externa do arquivo;
- validação estrutural e reparos seguros;
- inventário, armazém, itens equipados e referências por `UniqueId`;
- compatibilidade de slots, inclusive amuleto, brinco, anel e abraçadeira;
- encantamentos, tiers, `StatType`, `StatModKey`, `RecipeType` e contadores;
- autoequipe individual e distribuição global;
- perfis heurísticos dos seis heróis;
- desbloqueios locais conhecidos;
- fila de reciclagem;
- candidatos ao Mercado e isolamento de itens alterados/criados;
- consulta pública e cache do Steam Community Market;
- atualização do catálogo do jogo;
- interface e textos de segurança;
- entrada do código-fonte, PyInstaller, GitHub Actions, metadados e documentação.

## Achados críticos e altos encerrados

### Slot de amuleto

A antiga implementação tinha duas posições apontando para o prefixo de anel `62`. A inteligência atual usa os prefixos distintos:

- `60` — amuleto;
- `61` — brinco;
- `62` — anel;
- `63` — abraçadeira.

Há regressão automatizada específica para esse mapeamento.

### Pontuação lexicográfica de equipamento

A raridade deixou de decidir sozinha. A nota contínua atual combina raridade, nível quando disponível, tiers, ocupação dos encantamentos e afinidade do atributo com o perfil do herói.

Um equipamento de raridade imediatamente inferior pode superar outro vazio quando os encantamentos são suficientemente fortes e coerentes.

### Autoequipe sequencial

A distribuição entre heróis deixou de depender da ordem de `heroSaveDatas`. O alocador global usa cada item no máximo uma vez e impede que um herói seja rebaixado para aumentar a soma dos demais.

A solução foi confrontada com força bruta em 60 matrizes aleatórias durante a suíte de regressão.

### Modo Protegido e itens criados

Na versão anterior, o Modo Protegido limitava o tamanho de lotes, mas ainda permitia criar ou duplicar pequenas quantidades de itens. A 3.3.1 estabelece uma fronteira mais clara:

- criação de item é bloqueada enquanto o Modo Protegido estiver ativo;
- duplicação é bloqueada;
- item criado durante a sessão não pode ser equipado em Modo Protegido;
- itens criados ou modificados continuam excluídos da inteligência de Mercado;
- criação/duplicação local só volta a aparecer após desativação consciente do Modo Protegido.

### Detecção de mudança externa do save

A assinatura usada pelo Modo Protegido deixou de depender somente de `mtime` e tamanho. A camada final inclui SHA-256 do conteúdo do arquivo, de modo que uma alteração de mesmo tamanho com timestamp preservado também impede uma gravação sobre estado externo mais recente.

Há regressão que modifica o conteúdo mantendo tamanho e timestamp e confirma que a assinatura muda.

### Estado de integridade após falha de persistência

A geração dos bytes do `.es3` recalcula `SystemInfo`, mas uma falha posterior de `os.replace` não deve fazer a memória afirmar que um arquivo originalmente inválido foi reparado. A 3.3.1 usa `VerifiedSaveFile`, que restaura o estado anterior de `integrity_valid` quando a persistência falha e só mantém o estado reparado após gravação bem-sucedida.

O teste correspondente simula falha de disco, confirma que `integrity_valid` permanece falso e depois valida a recuperação por gravação normal e releitura.

### Caminho direto de alteração do save

`run_save_layer.py` permitia `set` e `import` arbitrários fora das validações da aplicação principal. Como não integrava o produto final nem o Modo Protegido, foi removido da distribuição-fonte.

### Duas entradas com comportamentos diferentes

O antigo `tbh_save_editor.py` ainda podia ser executado diretamente com lógica 3.2 em alguns pontos, embora o executável 3.3 usasse outra entrada.

Na 3.3.1:

- `legacy_editor.py` guarda o núcleo histórico utilizado internamente;
- `tbh_save_editor.py` é uma ponte de compatibilidade para imports e redireciona execução direta para a aplicação final;
- `hollyedittbh_final.py` é a entrada oficial;
- `HollyEditTBH.spec` empacota somente a entrada final.

A ponte é coberta por teste de importação e por smoke test de execução direta no Windows CI.

## Mercado Steam

A auditoria separa três conceitos que não devem ser confundidos:

1. qualidade de combate do item;
2. preço público observado;
3. elegibilidade real de listagem.

Encantamentos não melhoram artificialmente a prioridade de venda. Quantidade de anúncios concorrentes permanece informativa e não é usada como prova de liquidez ou demanda.

A preparação padrão trabalha com **4 slots por rodada**, coerente com a configuração-base publicada pelo desenvolvedor. O limite pode ser alterado pela variável `HOLLYEDIT_MARKET_SLOTS` somente quando a instalação efetivamente dispuser de mais slots.

A consulta do Steam Community Market:

- usa somente páginas públicas;
- não autentica a conta Steam;
- não usa cookies privados;
- não envia itens;
- mantém cache de baixa frequência;
- preserva um snapshot completo anterior quando uma nova coleta é parcial, ainda que a resposta parcial contenha mais linhas;
- não persiste coleta incompleta sobre um cache válido;
- não promete preço, venda, demanda ou elegibilidade.

### Política oficial considerada

Avisos oficiais do desenvolvedor consultados durante a auditoria:

- notícias oficiais do TBH: <https://steamcommunity.com/app/3678970/allnews/>;
- reabertura do Mercado em 25/06/2026: quatro slots de listagem, cooldown de oito horas por slot e restrição temporária para Cósmico, Divino e Celestial, com exceção indicada para Soulstones;
- atualização de 06/07/2026: o desenvolvedor informou sanções a usuários ligados a itens criados ou obtidos por métodos anormais e declarou que a liberação de negociação dos graus superiores dependeria de estabilidade e anúncio posterior.

A aplicação mantém política conservadora quando não existe confirmação oficial posterior de liberação.

## Catálogo de itens

A atualização do catálogo valida antes da substituição do cache:

- quantidade mínima plausível;
- `ItemKey` válido e sem duplicidade;
- presença dos tipos básicos esperados;
- diversidade mínima de raridades;
- proteção contra regressão abrupta em relação ao catálogo anterior;
- escrita atômica do cache somente após validação.

Uma resposta parcial do site não destrói silenciosamente uma base local íntegra.

## Save layer e integridade

Não foi encontrada falha objetiva que justificasse alteração da criptografia nesta release.

Foram preservados:

- AES-128-CBC do formato utilizado;
- derivação de chave existente;
- HMAC-SHA256 de `SystemInfo`;
- serialização interna;
- backup timestampado;
- escrita em arquivo temporário;
- `fsync` antes da substituição;
- `os.replace` para gravação atômica.

A camada final adiciona somente garantias operacionais ao redor desse núcleo: hash de conteúdo para detectar mudança externa e restauração do estado de integridade em falha de persistência. Os testes confirmam round-trip, detecção de integridade inválida, recálculo da assinatura, preservação do backup e comportamento correto em falha simulada de gravação.

## Encantamentos

A auditoria mantém validações para:

- quantidade de slots por raridade;
- `EnchantData` estruturado;
- `RecipeType` esperado pela posição;
- coerência `StatType` ↔ `StatModKey`;
- tier dentro de 0–30;
- `EnchantCount` coerente;
- atributos compatíveis com o equipamento;
- materiais sem encantamentos.

Não foi introduzida nova interpretação não confirmada do formato de encantamento.

## Heróis

Os seis perfis padrão permanecem explicitamente heurísticos:

- Cavaleiro — sobrevivência, vida, armadura e bloqueio;
- Arqueira — velocidade, crítico e projéteis;
- Feiticeiro — conjuração, recarga e área;
- Sacerdotisa — cura, recarga e disponibilidade de habilidades;
- Caçador — burst, crítico e projéteis;
- Matador — vida, sustentação e dano corpo a corpo.

Os testes verificam coerência funcional dos perfis, mas o programa não apresenta esses pesos como tier list oficial.

## Desbloqueios e limites deliberados

Mantidos como ações locais conservadoras:

- tutoriais;
- heróis;
- pets;
- grupos de atributos;
- receitas conhecidas da versão do save.

Não são forçados:

- conquistas Steam por API externa;
- cosméticos sem estrutura local conhecida;
- elegibilidade do Mercado;
- itens fabricados para venda por dinheiro real;
- progressão de servidor não representada de forma confiável no save.

## Limpeza da distribuição

Foram removidos da raiz:

- `AUDITORIA_v3.2.0.md`;
- `CHECKSUM_v3.2.0.txt`;
- `run_save_layer.py`.

O README foi atualizado para refletir a versão 3.3.1, a entrada suportada, todos os testes e os limites de segurança.

## CI e artefato

O workflow Windows final executa:

1. `actions/checkout@v7.0.1`;
2. `actions/setup-python@v7.0.0` com Python 3.12;
3. preparação do caminho de teste do Taskbar Hero;
4. `compileall`;
5. cinco suítes de regressão, totalizando 55 testes;
6. smoke test da ponte `tbh_save_editor.py`;
7. instalação do PyInstaller;
8. build do executável;
9. conferência de `FileVersion 3.3.1`;
10. smoke test do executável por cinco segundos;
11. geração de SHA-256;
12. `actions/upload-artifact@v7.0.1` com o executável e `SHA256SUMS.txt`.

O workflow roda em pull requests e em `push` para a `main`, evitando a antiga duplicação de gate em push de branch + PR. Também usa `permissions: contents: read` e controle de concorrência para cancelar execuções obsoletas do mesmo ref.

## Pendências que não bloqueiam a versão

- não existe garantia anti-banimento;
- alterações futuras no jogo podem exigir nova calibração de catálogo, versões de receitas ou regras de Mercado;
- o repositório ainda não automatiza uma GitHub Release/tag: o pacote validado é publicado pelo GitHub Actions;
- assinatura digital de código do executável não está configurada;
- o projeto não declara uma licença de distribuição no repositório; isso deve ser definido pelo mantenedor antes de eventual distribuição por terceiros.

## Parecer final

Com os gates descritos acima aprovados, não foi identificado defeito crítico conhecido que justifique bloquear a publicação da 3.3.1.

A versão é considerada tecnicamente apta para merge quando o CI do commit final estiver verde. O merge não substitui a necessidade de prudência: edição de saves de jogo conectado pode ser incompatível com regras futuras do desenvolvedor ou da Steam.
