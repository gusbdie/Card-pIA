document.addEventListener('DOMContentLoaded', () => {
    const processButton = document.getElementById('processButton');
    const textInput = document.getElementById('textInput');
    const resultContainer = document.getElementById('resultContainer');
    const resultArea = document.getElementById('resultArea');
    const loading = document.getElementById('loading');

    processButton.addEventListener('click', async () => {
        const texto = textInput.value.trim();
        
        if (!texto) {
            alert("Por favor, cole o texto do cardápio antes de processar.");
            return;
        }

        // Prepara a tela para o carregamento
        loading.classList.remove('d-none');
        resultContainer.classList.add('d-none');
        resultArea.textContent = "";
        processButton.disabled = true;

        try {
            // Formata o dado para enviar via POST
            const formData = new FormData();
            formData.append("texto", texto);

            // ==========================================
            // DEFINIÇÃO DA URL DO BACKEND NA NUVEM
            // ==========================================
            const BACKEND_URL = "https://cardapia.onrender.com";

            // Chama o Backend usando a variável configurada acima
            const response = await fetch(`${BACKEND_URL}/api/extract`, {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || "Erro desconhecido no servidor.");
            }

            const data = await response.json();
            
            // Exibe o JSON formatado bonitinho na tela
            resultArea.textContent = JSON.stringify(data, null, 2);
            resultContainer.classList.remove('d-none');

        } catch (error) {
            console.error(error);
            alert("Erro ao processar: " + error.message);
        } finally {
            // Finaliza o carregamento
            loading.classList.add('d-none');
            processButton.disabled = false;
        }
    });
});