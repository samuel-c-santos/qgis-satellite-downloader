# Configuração do Ambiente e Credenciais

Este documento descreve detalhadamente o processo de obtenção das credenciais necessárias para usar o Google Earth Engine (GEE) e o INPE.

> 💡 **Tutorial Completo**: Se você é iniciante no Google Earth Engine, segue um [tutorial passo a passo](https://samuelsantos.site/tutorial-gee-primeiros-passos/) que cobre desde a criação da conta até a configuração do ambiente.

## 1. Configuração do Arquivo .env

O sistema utiliza variáveis de ambiente para gerenciar configurações sensíveis. Crie um arquivo chamado `.env` na pasta do plugin baseado no modelo `.env.example`.

### Parâmetros Necessários:
- `GEE_PROJECT_ID`: O ID do seu projeto no Google Cloud.
- `GOOGLE_APPLICATION_CREDENTIALS_PATH`: O caminho relativo para o arquivo JSON da sua conta de serviço (ex: `secrets/chave.json`).
- `OUTPUT_DIR`: O diretório onde as imagens baixadas serão armazenadas.
- `INPE_EMAIL`: Seu email cadastrado no portal DGI do INPE.
- `INPE_PASSWORD`: Sua senha do portal DGI do INPE.

Exemplo de `.env`:
```env
GEE_PROJECT_ID=meu-projeto-gee
GOOGLE_APPLICATION_CREDENTIALS_PATH=secrets/minha-chave.json
OUTPUT_DIR=C:/Users/SeuUsuario/Downloads/imagens
INPE_EMAIL=meu@email.com
INPE_PASSWORD=minha-senha
```

## 2. Criação de Projeto no Google Cloud

Se você ainda não tem um projeto no Google Cloud:

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Clique no seletor de projetos (canto superior esquerdo) e depois em **"Novo Projeto"**.
3. Dê um nome ao projeto (ex: `meu-gee-downloader`) e clique em **Criar**.
4. Anote o **ID do projeto** (Project ID) - você precisará dele no arquivo `.env`.

## 3. Criação da Conta de Serviço (Google Cloud)

Para interagir com o Google Earth Engine localmente, é necessário possuir uma Conta de Serviço com as permissões adequadas.

### 3.1 Passos no Console do Google Cloud:
1. Acesse o console do [IAM & Admin](https://console.cloud.google.com/iam-admin/serviceaccounts).
2. Selecione o projeto desejado.
3. Clique em **Criar Conta de Serviço**.
4. Defina um nome para a conta (ex: `gee-downloader`) e prossiga.
5. Na etapa de permissões (Roles), adicione os seguintes papéis:
    - **Consumidor do Service Usage** (Service Usage Consumer): Necessário para permitir o uso da API pelo projeto.
    - **Visualizador de Recursos do Earth Engine** (Earth Engine Resource Viewer): Necessário para leitura de dados orbitais.
6. Conclua a criação da conta.

### 3.2 Geração da Chave JSON:
1. Na lista de contas de serviço, clique no e-mail da conta recém-criada.
2. Acesse a aba **Chaves** (Keys).
3. Clique em **Adicionar Chave** > **Criar nova chave**.
4. Selecione o formato **JSON** e clique em **Criar**.
5. O download do arquivo será iniciado automaticamente.

## 4. Armazenamento da Chave

1. Mova o arquivo JSON baixado para a pasta `secrets/` na raiz do projeto.
2. Certifique-se de que o nome do arquivo corresponde ao que foi definido na variável `GOOGLE_APPLICATION_CREDENTIALS_PATH` no seu arquivo `.env`.

## 5. Habilitação das APIs

Certifique-se de que as seguintes APIs estejam ativadas no seu projeto através da [Biblioteca de APIs](https://console.cloud.google.com/apis/library):
- Google Earth Engine API
- Service Usage API

## 6. Instalação no QGIS

Para que o plugin funcione corretamente dentro do QGIS, siga estes passos:

1. **Localize a pasta de plugins**:
   - No Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. **Copie a pasta**: Mova a pasta `qgis_satellite_downloader` deste repositório para o local acima.
3. **Verifique as dependências**: Abra o **OSGeo4W Shell** (instalado com o QGIS) como administrador e execute:
   ```bash
   python -m pip install earthengine-api requests python-dotenv
   ```
4. **Ative o plugin**: No QGIS, vá em `Complementos > Gerenciar e Instalar Complementos` e marque o **QGIS Satellite Downloader**.

## 7. Registro no Earth Engine

Contas de serviço novas devem estar registradas para uso com o Earth Engine. Caso encontre erros de acesso, verifique o registro no portal do [Earth Engine Cloud Projects](https://code.earthengine.google.com/register).
