'use strict';

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from "src/environments/environment";
import { Ontology } from '../models/ontology';

const BASE_URL = 'http://ontology-hub-demo.dev.ds.dataspaceunit.upm/dataset';

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
        const url = `${this.ontologyBaseUrl}/api/v2/vocabulary/list`;
        return this.http.get<Ontology[]>(url);
    }


}