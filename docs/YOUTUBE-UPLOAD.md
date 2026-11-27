# Publicação automática no YouTube

O recurso é opcional, sem serviços cloud do ShortForge e sem novas dependências Python.
Os arquivos são enviados diretamente à API oficial após TODOS os cortes validados.
O upload é sequencial. O servidor deve continuar aberto.

## Configuração inicial

1. Abra https://console.cloud.google.com/ e crie um projeto próprio.
2. Em APIs e serviços, habilite **YouTube Data API v3**.
3. Configure a tela de consentimento OAuth (Google Auth Platform), adicione seu
   próprio e-mail em usuários de teste, se estiver em Testing, e habilite os
   escopos youtube.upload e youtube.readonly. Autorize somente seu canal.
4. Crie um cliente OAuth **Aplicativo da Web** para o servidor HTTP local;
   em URIs de redirecionamento autorizados, adicione exatamente
   http://127.0.0.1:8766/oauth/callback. Baixe o JSON. No computador também
   é possível usar um cliente Desktop com redirecionamento loopback.
   No Termux é um servidor web local, não use credencial do tipo Android
   com loopback; a aceitação deste fluxo no Android precisa ser validada.
5. No próprio aparelho, na pasta ShortClips, com Python disponível:
   `python -m shortforge.youtube_upload connect /caminho/ao/client_secret.json`
   Abra a URL que aparecer no terminal no navegador do mesmo aparelho,
   escolha o canal e conceda as permissões. Não envie seu JSON ou tokens
   ao GitHub, chat ou outros usuários. As credenciais ficam em
   ~/.config/shortforge-youtube/ (diretório privado, fora de /sdcard).
6. Inicie o ShortForge normalmente. Abra Publicação automática no YouTube,
   clique Verificar canal, marque envio automático, escolha visibilidade,
   público infantil e intervalo. Confirme o lote quando clicar Gerar Shorts.

Primeiro teste: um Short privado. Confira o YouTube Studio. Depois configure
cinco. A conta pode aplicar visibilidade privada independentemente do pedido.
A configuração OAuth Testing pode expirar o refresh token em sete dias.
Agendamentos são enviados imediatamente como privados com publishAt futuro
(10 min após geração, mais o intervalo escolhido); precisam de tempo suficiente
para o envio. Não há geração semântica de títulos: nome original + corte + #Shorts.

## Retomar e desconectar

Pare o servidor antes de executar comandos de manutenção da fila, para evitar
dois processos enviando simultaneamente:
```
python -m shortforge.youtube_upload status
python -m shortforge.youtube_upload resume
python -m shortforge.youtube_upload disconnect
```
Resume continua sessões já registradas e envia pendências do canal conectado.
Se uma sessão expirar, não cria outro upload automaticamente: confira Studio.
O SQLite guarda ID do vídeo, hash por canal e sessão recuperável. Não apague
o banco para tentar novamente. Desconectar remove credenciais locais, mas não
exclui vídeos ou histórico. Revogue também o acesso na conta Google.
Se o servidor for interrompido antes de enfileirar, não enviará automaticamente
o lote antigo: gere um novo lote ou confira os resultados manualmente.
Nenhuma conta real foi conectada no desenvolvimento; teste real depende do OAuth.
