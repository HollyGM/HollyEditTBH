# Auditoria final — HollyEditTBH 3.1.0

Data: 12/08/2026

## Resultado

- 16 testes automatizados executados e aprovados.
- Executável final aberto com sucesso, responsivo e identificado como `HollyEditTBH v3.1.0`.
- Metadados do Windows confirmados: produto `HollyEditTBH`, versão de arquivo e produto `3.1.0`.
- Save real lido sem gravação: integridade válida, versão `1.01.05`, 6 heróis e 274 itens no momento da verificação.
- Nenhuma alteração foi gravada no save real durante a auditoria.

## Interface e usabilidade

- Revisão visual realizada em 1536×864 com escala do Windows de 125%.
- A antiga Central Inteligente foi convertida em **Assistente Guiado**.
- Cada tarefa informa o que faz, o que não faz e conduz por análise, prévia, confirmação e salvamento.
- Todos os botões foram mantidos visíveis nas abas Começar, Desbloqueios, Preparar Mercado, Separar reciclagem e Segurança.
- Busca e filtros de raridade/tipo foram reorganizados em duas linhas para não ficarem cortados.
- Colunas da lista principal foram ajustadas para exibir Local, Código, Nome, Raridade e ID único na tela.
- Janelas auxiliares agora respeitam a escala real do Windows e permanecem dentro da área visível.

## Funções verificadas

- abertura direta na pasta padrão do Taskbar Hero;
- leitura, criptografia, assinatura de integridade, backup e gravação atômica;
- criação, edição, busca, filtros e compatibilidade de encantamentos;
- retratos dos seis heróis;
- equipar melhor um herói e todos os heróis sem reutilizar o mesmo item;
- desbloqueios locais conservadores;
- análise de candidatos ao Mercado sem envio à Steam;
- separação de duplicados para reciclagem sem excluir ou converter itens;
- Modo Protegido, limite de lote, detecção do jogo aberto e de mudança externa do arquivo.

## Limpeza realizada

- 56 arquivos e 4 pastas, totalizando 86,5 MB de arquivos, foram enviados à Lixeira.
- Removidos: pacotes 2.x e 3.0, executável com nome antigo, capturas de teste, cópia de teste do save, dump legado, scripts antigos de alteração direta, cache de compilação e recursos duplicados da pasta `dist`.
- Permaneceram apenas o código atual, recursos necessários, testes, documentação e a entrega 3.1.0.

## Limites de segurança

- Não existe garantia anti-banimento. O programa reduz conflitos e erros, mas não burla regras ou detecção.
- A elegibilidade e o preço de Mercado são decididos pelo jogo e pela Steam.
- Feche o Taskbar Hero antes de salvar alterações.

## Entrega

- `HollyEditTBH.exe` — SHA-256 `818BBD6FB455A5CD568C44F505D98DB1DEFEAE116DD4C3AF2547DB74B53EEB07`
- `HollyEditTBH-v3.1.0.zip` — SHA-256 `899687D9F630542852F2B02434CB0B90D1756C0DC0D0E9CFA45484C3732DF85B`
