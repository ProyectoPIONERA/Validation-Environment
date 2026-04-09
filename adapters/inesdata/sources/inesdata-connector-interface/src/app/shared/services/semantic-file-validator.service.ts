import { Injectable } from "@angular/core";
import { rdfParser } from "rdf-parse";
import { Readable } from "readable-stream";


@Injectable({
    providedIn: 'root'
})
export class SemanticFileValidatorService{
    private readonly RDF_MIME_TYPES = [
        'text/turtle',
        'application/rdf+xml',
        'application/n-triples',
        'application/n-quads',
        'application/ld+json',
        'application/rdf+json',
        'text/n3'
    ];

    constructor(private rdfParser: RdfParser, private readable: Readable)
    {

    }

    async isASemanticFile(file: File): Promise<boolean> {
        try {
            const text = await file.text();              // ✅ siempre leemos el contenido
            const stream = Readable.from([text]);

            const quadStream = rdfParser.parse(stream, {
            contentType: file.type || 'application/octet-stream',
            path: file.name
            });

            return await new Promise<boolean>((resolve) => {
            quadStream.on('data', () => {
                quadStream.destroy();
                resolve(true);                           // ✅ detectado
            });

            quadStream.on('error', () => resolve(false)); // ✅ no es RDF
            quadStream.on('end', () => resolve(false));   // ✅ no se detectó RDF
            });

        } catch (e) {
            return false; // ✅ archivo ilegible, no es RDF
        }
    }

    
}