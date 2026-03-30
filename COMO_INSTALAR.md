# Guia de Instalação: QGIS Satellite Downloader (QGIS)

Este guia descreve os passos necessários para instalar e ativar o plugin de download de imagens orbitais (Landsat, Sentinel e CBERS-4A) no seu QGIS.

## 1. Preparação da Pasta

O plugin é fornecido como uma pasta chamada `qgis_satellite_downloader`. **Você precisará configurar suas próprias credenciais** (veja [CONFIGURACAO.md](CONFIGURACAO.md)). O arquivo `.env` e a pasta `secrets/` não acompanham o repositório por segurança - cada usuário deve criar as suas próprias credenciais.

### Passos:
1. Localize a pasta de plugins do seu perfil do QGIS no Windows:
   *   Pressione `Win + R` e cole o seguinte caminho:
       `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. Copie a pasta inteira `qgis_satellite_downloader` para dentro deste diretório.

## 2. Instalação de Dependências (Obrigatório)

O plugin utiliza bibliotecas avançadas (Google Earth Engine e INPE) que não vêm por padrão no QGIS. Você tem duas formas de instalar:

### Opção A: Pelo próprio Plugin (Recomendado ⭐)
1. Abra o QGIS e ative o plugin (veja o item 3 abaixo).
2. Se aparecer um **Botão Laranja** escrito `⚠️ Erro nas ferramentas CBERS`, clique em **"FORÇAR REINSTALAÇÃO CBERS"**.
3. Aguarde o aviso de sucesso e **reinicie o QGIS**.

### Opção B: Pelo OSGeo4W Shell (Manual)
1. Feche o QGIS.
2. No menu Iniciar, procure por **OSGeo4W Shell** e execute como **Administrador**.
3. Cole o comando:
   ```bash
   python -m pip install --upgrade --force-reinstall cbers4asat rasterio geopandas shapely scikit-image geomet geojson "numpy<2.0"
   ```

## 3. Ativação do Plugin no QGIS

1. Abra o QGIS.
2. No menu superior, vá em **Complementos** > **Gerenciar e Instalar Complementos...**.
3. No painel à esquerda, clique em **Instalados**.
4. Procure por **QGIS Satellite Downloader** na lista e marque a caixa de seleção ao lado do nome.
5. O ícone do plugin (logotipo do IDEFLOR ou ícone de download) aparecerá na sua barra de ferramentas.

## 4. Primeiro Uso e Dicas

*   **Área de Interesse**: Você pode definir a área de download usando a tela atual do seu mapa ou selecionando a extensão de uma camada (shapefile ou raster) que já esteja no seu projeto.
*   **Buffer**: Se a imagem parecer muito "justa" na borda, use as **Opções Avançadas** para aumentar o "Fator de Buffer".
*   **CBERS-4A**: Para usar o CBERS, é necessário criar uma conta gratuita no portal **DGI do INPE**:
    1. Acesse o portal: [INPE Explorer](http://www.dgi.inpe.br/catalogo/explore)
    2. Clique em **"Entrar"** (canto superior direito)
    3. Selecione **"Criar conta"** ou use uma conta Google/Apple existente
    4. Preencha os dados solicitados (nome, email, organização, etc.)
    5. Após confirmar o cadastro, você terá acesso ao catálogo CBERS-4A
    6. **No arquivo `.env`**, configure:
        ```env
        INPE_EMAIL=seu-email-que-voce-usou-no-cadastro
        INPE_PASSWORD=sua-senha-do-portal-inpe
        ```
    - O plugin usará essas credenciais para autenticar e baixar as imagens do catálogo INPE.
*   **Destino**: Certifique-se de escolher uma pasta de saída onde você tenha permissão de escrita.

---
**Suporte**: Samuel Santos
