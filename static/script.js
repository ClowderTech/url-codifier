document.addEventListener('DOMContentLoaded', function () {
    var editor = CodeMirror(document.getElementById('code-editor'), {
        value: '',
        mode: 'python',
        lineNumbers: true,
        theme: 'default',
        lineWrapping: true,
        matchBrackets: true,
        autoCloseBrackets: true,
        autoCloseTags: true,
        showCursorWhenSelecting: true,
        indentUnit: 4,
        tabSize: 4,
        // Removed scrollbarStyle to prevent the error
    });

    // Sync CodeMirror content with hidden textarea
    editor.on('change', function(cm, change) {
        document.getElementById('code').value = cm.getValue();
    });
});
