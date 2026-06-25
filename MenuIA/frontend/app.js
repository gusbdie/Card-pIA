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

            // Chama o Backend local rodando na porta 8080
            const response = await fetch("https://cardapia.onrender.com", {
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