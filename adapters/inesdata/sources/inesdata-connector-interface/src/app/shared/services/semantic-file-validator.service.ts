import { Injectable } from "@angular/core";
import * as $rdf from "rdflib";

@Injectable({
  providedIn: "root",
})
export class SemanticFileValidatorService {

  // Formatos soportados por rdflib en navegador
  private readonly FORMATS = [
    "text/turtle",             // Turtle
    "application/rdf+xml",     // RDF/XML
    "application/ld+json",     // JSON-LD
    "text/n3"                  // Notation3
  ];

  private readonly BASE_IRI = "urn:semantic-file:"; // identificador ficticio

  constructor() {}

  async isASemanticFile(file: File): Promise<boolean> {
    try {
      const text = await file.text();
      const store = $rdf.graph();

      for (const format of this.FORMATS) {
        try {
          // Intentamos parsear en cada formato conocido
          $rdf.parse(text, store, this.BASE_IRI, format);
          return true; // ✅ El archivo contiene RDF válido
        } catch (e) {
          // fallo → probar siguiente formato
        }
      }

      return false; // ❌ Ningún formato RDF lo pudo interpretar

    } catch {
      return false; // ❌ error leyendo archivo → no es semántico
    }
  }
}