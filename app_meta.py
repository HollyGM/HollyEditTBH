"""Single source of truth for HollyEditTBH application metadata."""

APP_NAME = "HollyEditTBH"
APP_VERSION = "3.4.3"
__version__ = APP_VERSION

#: AppID do TBH: Task Bar Hero publicado na Steam. Serve tanto à URL de busca do
#: Mercado quanto à localização do prefixo Proton/Wine que guarda o save.
#:
#: Estava declarado duas vezes com valores diferentes: ``market_policy`` usava o
#: valor correto e ``platform_support`` usava 2957000, de modo que a procura do
#: save no Linux apontava para uma pasta ``compatdata`` que não existe.
STEAM_APP_ID = 3678970

#: AppID do playtest/demo. Não recebe Mercado, mas quem jogou aquela versão pode
#: ter um save sob o prefixo dela, então continua valendo como último recurso na
#: descoberta do caminho.
STEAM_PLAYTEST_APP_ID = 2957000
