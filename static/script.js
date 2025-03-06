document.addEventListener('DOMContentLoaded', function () {
    var editor = CodeMirror(document.getElementById('code-editor'), {
        value: 'async def main():\n    return ""', // Prefill the editor with the template
        mode: 'python',
        lineNumbers: true,
        theme: 'material', // Ensure this matches your chosen dark theme
        lineWrapping: true,
        matchBrackets: true,
        autoCloseBrackets: true,
        autoCloseTags: true,
        showCursorWhenSelecting: true,
        indentUnit: 4,
        tabSize: 4,
    });

    // Sync CodeMirror content with hidden textarea
    editor.on('change', function(cm, change) {
        document.getElementById('code').value = cm.getValue();
    });
});
