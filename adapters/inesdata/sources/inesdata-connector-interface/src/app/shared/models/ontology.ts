export interface Ontology {
  uri: string
  nsp: string
  prefix: string
  titles: OntologyTitle[]
}

export interface OntologyTitle {
  value: string
  lang: string
  _id: string
}
