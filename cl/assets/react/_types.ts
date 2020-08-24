export interface Tag {
  id: number;
  name: string;
  dockets: number[];
  assocId?: number;
}
export interface Association {
  id: number;
  tag: number;
  docket: number;
}
export interface ApiResult<T> {
  count: number;
  next: string;
  previous: string;
  results: T[];
}
