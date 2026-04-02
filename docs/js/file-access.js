/**
 * File System Access API wrapper — read/write local folders from the browser.
 *
 * Requires Chrome 86+ or Edge 86+. Falls back to file input for other browsers.
 */

class FileAccess {
    constructor() {
        this.directoryHandle = null;
        this.supported = 'showDirectoryPicker' in window;
    }

    async openDirectory() {
        if (!this.supported) {
            throw new Error('File System Access API not supported. Use Chrome or Edge.');
        }
        this.directoryHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
        return this.directoryHandle.name;
    }

    get isOpen() {
        return this.directoryHandle !== null;
    }

    async readFile(name) {
        if (!this.directoryHandle) throw new Error('No directory open');
        const fileHandle = await this.directoryHandle.getFileHandle(name);
        const file = await fileHandle.getFile();
        return file.text();
    }

    async writeFile(name, content) {
        if (!this.directoryHandle) throw new Error('No directory open');
        const fileHandle = await this.directoryHandle.getFileHandle(name, { create: true });
        const writable = await fileHandle.createWritable();
        await writable.write(content);
        await writable.close();
    }

    async listFiles(extension = null) {
        if (!this.directoryHandle) throw new Error('No directory open');
        const files = [];
        for await (const entry of this.directoryHandle.values()) {
            if (entry.kind === 'file') {
                if (!extension || entry.name.endsWith(extension)) {
                    files.push(entry.name);
                }
            }
        }
        return files;
    }

    async syncToFolder(data) {
        const json = JSON.stringify(data, null, 2);
        await this.writeFile('growthchart-data.json', json);
    }

    async syncFromFolder() {
        try {
            const json = await this.readFile('growthchart-data.json');
            return JSON.parse(json);
        } catch (e) {
            return null;
        }
    }
}

if (typeof module !== 'undefined') module.exports = FileAccess;
