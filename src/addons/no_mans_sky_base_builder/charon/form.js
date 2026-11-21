// Executed only on Charon's upload page after its account check succeeds.
(build => {
    if (location.origin !== 'https://charon.gg' || location.pathname !== '/ships/upload/') return 'Page changed';
    const byId = id => document.getElementById(id);
    const form = byId('uploadForm');
    if (form?.dataset.bbeReady) return '';
    const base = build.kind === 'base';
    const radio = (name, value) => form?.querySelector('input[name="' + name + '"][value="' + value + '"]');
    const file = byId(base ? 'ufBaseFile' : 'ufFileInput');
    const kind = radio('ufKind', base ? 'base' : 'corvette');
    const method = radio(base ? 'baseFileMethod' : 'uploadMethod', 'file');
    const buildMethod = radio('buildMethod', 'blender');
    const name = byId('ufName');
    if (!form || !file || !kind || !method || !buildMethod || !name || !byId('ufSubmitBtn') || !byId('uploadThanks'))
        return 'Charon’s form has changed. The build could not be attached.';
    kind.click();
    method.click();
    buildMethod.click();
    const bytes = Uint8Array.from(atob(build.bytes), c => c.charCodeAt(0));
    const filename = (build.name.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').slice(0, 80) || 'build') +
        (base ? '.json' : '.nmsship');
    const transfer = new DataTransfer();
    transfer.items.add(new File([bytes], filename, {type: base ? 'application/json' : 'application/octet-stream'}));
    file.files = transfer.files;
    file.dispatchEvent(new Event('change', {bubbles:true}));
    if (byId(base ? 'ufBaseFileName' : 'ufFileSelectedName')?.textContent !== filename)
        return 'Charon did not accept the attached build. Check its format and size.';
    name.value = build.name.slice(0, name.maxLength > 0 ? name.maxLength : 60);
    name.dispatchEvent(new Event('input', {bubbles:true}));

    // Keep the website's actual controls and handlers, including its photo labels,
    // visibility choices, validation messages, and the builder's agreement.
    const page = byId('uploadPage');
    for (let node = page; node && node !== document.body; node = node.parentElement) {
        for (const sibling of node.parentElement.children) {
            if (sibling !== node && !['SCRIPT', 'STYLE', 'LINK'].includes(sibling.tagName))
                sibling.classList.add('bbe-outside');
        }
    }
    const attached = document.createElement('div');
    attached.className = 'bbe-attached';
    attached.textContent = (base ? 'Base' : 'Corvette') + ' · ' + filename;
    form.prepend(attached);
    const editor = document.createElement('section');
    editor.className = 'bbe-editor';
    attached.after(editor);
    function field(title, control, wide = false) {
        const label = document.createElement('label');
        if (wide) label.className = 'bbe-wide';
        label.append(title, control);
        editor.append(label);
    }
    function textField(title, original, multiline = false) {
        const control = document.createElement(multiline ? 'textarea' : 'input');
        control.value = original.value;
        control.required = true;
        if (original.maxLength > 0) control.maxLength = original.maxLength;
        if (multiline) { control.rows = 2; control.minLength = 10; }
        control.addEventListener('input', () => {
            original.value = control.value;
            original.dispatchEvent(new Event('input', {bubbles:true}));
        });
        field(title, control, multiline);
    }
    function choice(title, inputs, caption) {
        const select = document.createElement('select');
        if (!inputs.some(input => input.checked)) select.add(new Option('Choose…', ''));
        for (const input of inputs) select.add(new Option(caption(input), input.value, false, input.checked));
        select.required = true;
        select.addEventListener('change', () => inputs.find(input => input.value === select.value)?.click());
        field(title, select);
    }
    function toggles(title, buttons, caption) {
        const group = document.createElement('fieldset');
        const legend = document.createElement('legend');
        legend.textContent = title;
        group.append(legend);
        for (const original of buttons) {
            const label = document.createElement('label'), box = document.createElement('input');
            box.type = 'checkbox';
            box.checked = original.checked || original.getAttribute('aria-pressed') === 'true';
            box.addEventListener('change', () => original.click());
            label.append(box, caption(original));
            group.append(label);
        }
        editor.append(group);
    }
    const radios = key => Array.from(form.querySelectorAll('input[name="' + key + '"]'));
    const labelText = input => input.closest('label').textContent.trim();
    textField(base ? 'Base name' : 'Ship name', name);
    choice('Visibility', radios('visibility'), input => input.closest('label').querySelector('.up-opt-name').textContent);
    textField('Description', byId('ufDescription'), true);
    choice('Build method', radios('buildMethod'), labelText);
    if (base) choice('Base category', radios('ufBaseCat'), labelText);
    else {
        toggles('Cockpit view', [byId('ufPovFirst'), byId('ufPovThird')], labelText);
        toggles('Categories', form.querySelectorAll('[data-cat]'), button => button.textContent.trim());
    }
    // Keep the site's controls for optional metadata available in one disclosure.
    const optional = document.createElement('details');
    optional.className = 'bbe-more';
    const summary = document.createElement('summary');
    summary.textContent = 'Additional listing details';
    optional.append(summary);
    byId('ufStepDetails').before(optional);
    optional.append(byId('ufStepShip'), byId('ufStepDetails'));
    for (const original of [name, byId('ufDescription'), buildMethod, byId('ufCategory'), byId('ufPovFirst'), radio('ufBaseCat','land')])
        original?.closest('.up-f, .up-row')?.classList.add('bbe-outside');
    const amenities = byId('ufStepAmen');
    if (amenities) {
        const more = document.createElement('details');
        more.className = 'bbe-more';
        const label = document.createElement('summary');
        label.textContent = 'Amenities and notes';
        more.append(label);
        amenities.before(more);
        more.append(amenities);
    }
    // Retain the attached file and selected build kind throughout this upload.
    for (const id of ['ufStepKind','ufStepWhere','ufStepMethod','ufBaseFileBlock','ufDraftBtn'])
        byId(id)?.classList.add('bbe-outside');
    const style = document.createElement('style');
    style.textContent = `
        .bbe-outside, .up-left, .up-right, .up-crumb, .up-bar, .up-num, .up-opt-sub {display:none!important}
        html,body {min-width:0!important;padding:0!important;margin:0!important;background:#27292c!important}
        #uploadPage {box-sizing:border-box;width:100%;max-width:850px;margin:auto;padding:10px 18px 18px}
        #uploadForm,.up-split,.up-main {width:auto!important;max-width:none!important;margin:0!important;padding:0!important}
        .up-split {display:block!important}
        .up-main {display:flex!important;flex-direction:column;gap:6px!important}
        #uploadPage .up-step,#uploadPage .up-finish,.bbe-more {margin:0;padding:9px 11px;border:1px solid #484b50;border-radius:5px;background:#303236}
        .up-step-h {font:600 14px system-ui!important;margin:0 0 6px!important}
        .up-step-h[hidden],[hidden]{display:none!important}
        .up-rows,.up-grid,.up-stack {gap:6px!important}
        .up-row,.up-block {padding-block:4px!important;margin-block:0!important}
        .up-row-k {min-width:100px}
        .up-ta {min-height:44px!important;height:52px}
        .up-opt,.up-tog {padding:4px 8px!important}
        .bbe-attached, .bbe-more summary {color:#e3e9f0;font:600 13px system-ui;padding:5px 0 10px}
        .bbe-editor {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 12px;margin-bottom:8px;padding:12px;border:1px solid #484b50;border-radius:5px;background:#303236;color:#eee;font:13px system-ui}
        .bbe-editor>label {display:grid;gap:3px;align-content:start}
        .bbe-editor input:not([type=checkbox]),.bbe-editor select,.bbe-editor textarea {box-sizing:border-box;width:100%;color:#eee;background:#202226;border:1px solid #585c64;border-radius:4px;padding:5px 7px;font:inherit}
        .bbe-editor textarea {resize:vertical;min-height:46px}
        .bbe-editor .bbe-wide,.bbe-editor fieldset:last-child {grid-column:1/-1}
        .bbe-editor fieldset {border:0;padding:0;min-width:0;margin:0}
        .bbe-editor legend {padding:0;margin:0 0 4px}
        .bbe-editor fieldset label {display:inline-flex;align-items:center;gap:4px;margin:0 10px 3px 0}
        .bbe-more .up-step-h {display:none}
        .bbe-more summary {cursor:pointer;padding:2px}
        .bbe-more #ufStepAmen {border:0;padding:6px 0}
        .bbe-more .up-step-h {display:none}
        #ufStepShip {order:-3} #ufStepDetails {order:-2} #ufStepPhotos {order:-1}
        .up-finish {order:2}
    `;
    document.head.append(style);
    form.dataset.bbeReady = '1';
    return '';
})

