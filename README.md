# Windguru SAP — Clássico/Madeirol

Extensão do `collector.py` original localizado em `Flowers Solutions/Windguru SAP`.
O original e seu banco no OneDrive foram preservados. Copie os arquivos desta pasta
para o projeto, mantendo o `windguru_sap.db` existente. Inclua a pasta oculta `.github`.

## O que mudou

- Mantidas as funções de coleta, coordenadas, unidades e tabela `previsoes_brutas`.
- Vento e ondas unidos pelo timestamp; respostas incompatíveis falham antes da gravação.
- `forecast_hours=72` busca 72 horas desde a hora atual. O original usava três dias
  desde meia-noite, que não equivalem a 72 horas futuras.
- Após salvar, `pipeline.py` lê a hora atual em America/Sao_Paulo do último lote.
  Não percorre as 72 horas disparando alertas de mudanças futuras.
- Plugin recebe `Metrics` e devolve `Verdict(classification, reason)` ou `None`.
- Direção do vento é removida antes de chamar o plugin quando velocidade < limiar.
  Igual ao limiar conta como relevante. Velocidade ausente ou direção ausente com
  vento relevante suspendem o veredicto. Valores inválidos viram `None`.
- `ultimo_estado_notificado` é criada sem alterar a tabela original. A comparação
  usa somente o texto da classificação, não horário, motivo ou números da previsão.
  Primeiro veredicto válido notifica; A→A não; A→B e B→A notificam.
- Estado é atualizado apenas após confirmação do provedor. Falha permite tentar
  novamente no próximo ciclo; ausência de regra/dados e simulação preservam estado.

## Regras pessoais (pendentes de você)

Edite `spot_rules.py`: defina `WIND_RELEVANT_KMH` em km/h e implemente `classify`.
Nenhum limiar de surf foi inventado. Com o arquivo entregue, a coleta funciona,
mas não há veredictos nem notificações. Verifique `None` em cada métrica usada.
Direção `None` com vento fraco é esperada e não deve piorar a classificação.
Use sempre o mesmo texto para a mesma classe. Alterar o texto conta como mudança.

Para outro conjunto de regras, crie um módulo com o mesmo contrato e configure
`SAP_RULES_MODULE=nome_do_modulo`. O pipeline e a persistência não precisam mudar.
O motor evita dados com mais de três horas e não usa lotes antigos como fallback.

## Instalar e testar localmente

Python 3.12 ou superior:

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python collector.py
```

O padrão é simulação (`SAP_DRY_RUN=1`): grava dados e mostra veredicto, sem enviar
nem registrar estado notificado. Para enviar, use `SAP_DRY_RUN=0` e as duas
credenciais abaixo como variáveis de ambiente. `SAP_DB_PATH` permite outro caminho
para o banco (padrão: `windguru_sap.db` no diretório de execução).

## Pushover e secrets

Recomendação: Pushover pela API simples e foco em notificações pessoais no iPhone.
A tabela oficial informa US$ 4,99 por plataforma, compra única, teste de 30 dias
e 10.000 mensagens/mês gratuitas. Confira o preço local na App Store.

1. Instale Pushover no iPhone, crie conta e permita notificações.
2. No painel Pushover, copie sua **User Key**.
3. Registre uma aplicação chamada Windguru SAP e copie seu **API Token**.
4. No repositório GitHub, abra **Settings → Secrets and variables → Actions →
   Secrets → New repository secret** e crie:

| Secret | Conteúdo |
| --- | --- |
| `PUSHOVER_APP_TOKEN` | API Token da aplicação |
| `PUSHOVER_USER_KEY` | User Key da sua conta |

Não escreva credenciais no código, SQLite ou YAML. O `GITHUB_TOKEN` é fornecido
automaticamente pelo Actions; não precisa criar PAT. Para trocar de serviço,
implemente `Notifier.send(title, message)` e injete em `evaluate_latest`.

## GitHub Actions — a cada duas horas

1. Coloque estes arquivos na raiz de um repositório, preferencialmente privado,
   na branch padrão. O YAML fica em `.github/workflows/surf.yml`.
2. Permita Actions e gravação de conteúdo pelo workflow; políticas da organização
   e regras de branches precisam permitir que `GITHUB_TOKEN` atualize `sap-state`.
3. Na primeira execução, abra **Actions → Windguru SAP → Run workflow**, marque
   `initialize_state`. Isso cria a branch `sap-state` com um SQLite vazio. O
   histórico local não é importado automaticamente. Para continuá-lo, coloque
   uma cópia consistente do banco existente nessa branch antes do primeiro envio.
4. Execute em simulação e confira os logs. Implemente suas regras e seus secrets.
5. Em **Settings → Secrets and variables → Actions → Variables**, crie
   `SAP_DRY_RUN` com valor `0` para ativar envios. `1` volta à simulação.

O cron `17 */2 * * *` roda no minuto 17 a cada duas horas, em UTC. Para uma hora,
use `17 * * * *`; para três, `17 */3 * * *`. O GitHub pode atrasar ou descartar
execuções sob carga; o cron não é um relógio exato. Workflows agendados precisam
estar na branch padrão; repositórios públicos podem ter o cron desativado após
60 dias sem atividade.

### Persistência entre máquinas temporárias do Actions

Cada execução restaura o SQLite completo de `sap-state` e salva uma cópia com
SQLite Backup após o pipeline, inclusive em falha normal. Essa branch é durável,
sem depender da expiração de cache/artifact. `concurrency` serializa os jobs.
Se a branch faltar, uma execução normal falha antes de enviar: não reinicializa
silenciosamente a deduplicação. Não apague a branch nem marque inicialização para
recuperar uma perda de estado sem antes restaurar seu backup.

Use apenas um agendador de envio. Processos com o mesmo arquivo SQLite são
serializados com `BEGIN IMMEDIATE`, mas uma execução local e uma remota com cópias
distintas não compartilham estado. O histórico bruto cresce e também ocupa espaço
no Git; para este uso pessoal é simples, mas monitore o tamanho do repositório.

Não há transação única entre Pushover, SQLite e GitHub. Timeout após aceitação,
queda após envio, cancelamento forçado ou falha ao publicar a branch podem causar
uma repetição no próximo ciclo. Falhas de persistência aparecem no Actions e devem
ser resolvidas antes de novas execuções. Confirmação da API significa aceitação
pelo serviço, não comprovação de que você leu o alerta no iPhone.

## Validação

Testes isolados com respostas simuladas cobrem união por horário, rejeição de
desalinhamento, limiar de vento, regras pendentes, persistência entre conexões,
mudanças A→B→A, falha no envio, hora local, dados antigos e simulação. Nenhuma
notificação real foi enviada. A execução remota depende do repositório e secrets.

## Documentação consultada em 14/09/2026

- [Open-Meteo Marine](https://open-meteo.com/en/docs/marine-weather-api)
- [Open-Meteo Forecast](https://open-meteo.com/en/docs)
- [Pushover API e registro da aplicação](https://pushover.net/api)
- [Pushover preços](https://pushover.net/pricing)
- [GitHub schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [actions/checkout](https://github.com/actions/checkout)
- [actions/setup-python](https://github.com/actions/setup-python)

Dados meteorológicos: Open-Meteo. Nenhum scraping do Windguru.
