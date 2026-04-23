'use strict';

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from "src/environments/environment";
import { Ontology } from '../models/ontology';

const BASE_URL = 'http://ontology-hub-demo.dev.ds.dataspaceunit.upm';
const ADMIN_USER = 'admin@gmail.com';
const ADMIN_PASSWORD = 'admin1234';

@Injectable({
  providedIn: 'root'
})
export class OntologyService{
    
    public constructor(private http: HttpClient){

    }

    get ontologyBaseUrl(): string {
        return  environment.runtime.ontologyUrl || BASE_URL;
    }

    public getOntologyLists(): Observable<Ontology[]> {
        const url = `${this.ontologyBaseUrl}/dataset/api/v2/vocabulary/list`;
        return this.http.get<Ontology[]>(url);
    }

    public postUploadShacl(file: File, prefix: string, vocabUrl: string): Observable<any> {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('user', ADMIN_USER);
        formData.append('password', ADMIN_PASSWORD);
        formData.append('prefix', prefix);
        formData.append('vocabUrl', vocabUrl);

        const url = `${this.ontologyBaseUrl}/dataset/api/v2/vocabulary/artifacts/shapes`;
        return this.http.post(url, formData);
    }

    /**
     * BuildingUrl
     * For re construct ontology hub Urls for ontology and shacl files
     */
    public buildUrl(prefix: string, type: "ontology" | "shacl", version: string|null):string{
        //Ontologia http://ontology-hub-demo.dev.ds.dataspaceunit.upm/dataset/vocabs/s4auto/versions/2026-04-16.n3
        //Shacl http://ontology-hub-demo.dev.ds.dataspaceunit.upm/dataset/vocabs/s4auto/artifacts/shapes/TestGeneradosSaref4Grid.txt
        console.log(prefix, type, version);
        let url = `${this.ontologyBaseUrl}/dataset/vocabs/${prefix}`;
        if(type === 'ontology'){
            url += `/versions/${version}.n3`;
        }else if(type === 'shacl' ){
            url += `/artifacts/shapes/${version}`;
        }
        console.log(url);
        return url;
    }
}